from decimal import Decimal
import logging
import stripe
from django.conf import settings
from django.utils.translation import ugettext as _
from corehq.apps.accounting.models import PaymentRecord, CreditLine
from corehq.apps.accounting.utils import fmt_dollar_amount

stripe.api_key = settings.STRIPE_PRIVATE_KEY
logger = logging.getLogger('accounting')

def get_or_create_stripe_customer(payment_method):
    customer = None
    if payment_method.customer_id is not None:
        try:
            customer = stripe.Customer.retrieve(payment_method.customer_id)
        except stripe.InvalidRequestError:
            pass
    if customer is None:
        customer = stripe.Customer.create(
            description="Account Admin %(web_user)s for %(domain)s, "
                        "Account %(account_name)s" % {
                'web_user': payment_method.billing_admin.web_user,
                'domain': payment_method.billing_admin.domain,
                'account_name': payment_method.account.name,
            },
            email=payment_method.billing_admin.web_user,
        )
    payment_method.customer_id = customer.id
    payment_method.save()
    return customer


class BaseStripePaymentHandler(object):
    """Handler for paying via Stripe's API
    """

    def __init__(self, payment_method):
        self.payment_method = payment_method

    @property
    def cost_item_name(self):
        """Returns a name for the cost item that's used in the logging messages.
        """
        raise NotImplementedError("you must implement cost_item_name")

    def create_charge(self, amount, card=None, customer=None):
        """Process the HTTPRequest used to make this payment

        returns a dict to be used as the json response for the request.
        """
        raise NotImplementedError("you must implement process_request")

    def get_charge_amount(self, request):
        """Returns a Decimal of the amount to be charged.
        """
        raise NotImplementedError("you must implement get_charge_amount")

    def update_credits(self, payment_record):
        """Updates any relevant Credit lines
        """
        raise NotImplementedError("you must implement update_credits")

    def get_amount_in_cents(self, amount):
        amt_cents = amount * Decimal('100')
        return int(amt_cents.quantize(Decimal(10)))

    def process_request(self, request):
        customer = None
        amount = self.get_charge_amount(request)
        card = request.POST.get('stripeToken')
        remove_card = request.POST.get('removeCard')
        is_saved_card = request.POST.get('selectedCardType') == 'saved'
        save_card = request.POST.get('saveCard') and not is_saved_card
        generic_error = {
            'error': {
                'message': _(
                    "Something went wrong while processing your payment. "
                    "We're working quickly to resolve the issue. No charges "
                    "were issued. Please try again in a few hours."
                ),
            },
        }
        try:
            if remove_card:
                customer = get_or_create_stripe_customer(self.payment_method)
                customer.cards.retrieve(card).delete()
                return {
                    'success': True,
                    'removedCard': card,
                }
            if save_card:
                customer = get_or_create_stripe_customer(self.payment_method)
                card = customer.cards.create(card=card)
                customer.default_card = card
                customer.save()
                card = card
            if is_saved_card:
                customer = get_or_create_stripe_customer(self.payment_method)
            charge = self.create_charge(amount, card=card, customer=customer)
            payment_record = PaymentRecord.create_record(
                self.payment_method, charge.id, amount
            )
            self.update_credits(payment_record)
        except stripe.error.CardError as e:
            # card was declined
            return e.json_body
        except (
            stripe.error.AuthenticationError,
            stripe.error.InvalidRequestError,
            stripe.error.APIConnectionError,
            stripe.error.StripeError,
        ) as e:
            logger.error(
                "[BILLING] A payment for %(cost_item)s failed due "
                "to a Stripe %(error_class)s: %(error_msg)s" % {
                    'error_class': e.__class__.__name__,
                    'cost_item': self.cost_item_name,
                    'error_msg': e.json_body['error']
                })
            return generic_error
        except Exception as e:
            logger.error(
                "[BILLING] A payment for %(cost_item)s failed due "
                "to: %(error_msg)s" % {
                    'cost_item': self.cost_item_name,
                    'error_msg': e,
                })
            return generic_error
        return {
            'success': True,
            'card': card,
            'wasSaved': save_card,
        }


class InvoiceStripePaymentHandler(BaseStripePaymentHandler):

    def __init__(self, payment_method, invoice):
        super(InvoiceStripePaymentHandler, self).__init__(payment_method)
        self.invoice = invoice

    @property
    def cost_item_name(self):
        return _("Invoice #%s") % self.invoice.id

    def create_charge(self, amount, card=None, customer=None):
        return stripe.Charge.create(
            card=card,
            customer=customer,
            amount=self.get_amount_in_cents(amount),
            currency=settings.DEFAULT_CURRENCY,
            description="Payment for Invoice %s" % self.invoice.invoice_number,
        )

    def get_charge_amount(self, request):
        """Returns a Decimal of the amount to be charged.
        """
        if request.POST['paymentAmount'] == 'full':
            return self.invoice.balance.quantize(Decimal(10) ** -2)
        return Decimal(request.POST['customPaymentAmount'])

    def update_credits(self, payment_record):
        # record the credit to the account
        CreditLine.add_credit(
            payment_record.amount, account=self.invoice.subscription.account,
            payment_record=payment_record,
        )
        CreditLine.add_credit(
            -payment_record.amount,
            account=self.invoice.subscription.account,
            invoice=self.invoice,
        )
        self.invoice.update_balance()
        self.invoice.save()


class CreditStripePaymentHandler(BaseStripePaymentHandler):

    def __init__(self, payment_method, account, subscription=None,
                 product_type=None, feature_type=None):
        super(CreditStripePaymentHandler, self).__init__(payment_method)
        self.product_type = product_type
        self.feature_type = feature_type
        self.account = account
        self.subscription = subscription

    @property
    def cost_item_name(self):
        return "%(credit_type)s Credit %(sub_or_account)s" % {
            'credit_type': ("%s Product" % self.product_type
                            if self.product_type is not None
                            else "%s Feature" % self.feature_type),
            'sub_or_account': ("Subscription %s" % self.subscription
                               if self.subscription is None
                               else "Account %s" % self.account.id),
        }

    def get_charge_amount(self, request):
        return Decimal(request.POST['amount'])

    def create_charge(self, amount, card=None, customer=None):
        return stripe.Charge.create(
            card=card,
            customer=customer,
            amount=self.get_amount_in_cents(amount),
            currency=settings.DEFAULT_CURRENCY,
            description="Payment for %s" % self.cost_item_name,
        )

    def update_credits(self, payment_record):
        self.credit_line = CreditLine.add_credit(
            payment_record.amount, account=self.account, subscription=self.subscription,
            product_type=self.product_type, feature_type=self.feature_type,
            payment_record=payment_record,
        )

    def process_request(self, request):
        response = super(CreditStripePaymentHandler, self).process_request(request)
        if hasattr(self, 'credit_line'):
            response.update({
                'balance': fmt_dollar_amount(self.credit_line.balance),
            })
        return response
