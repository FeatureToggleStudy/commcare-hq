from custom.ewsghana.handlers import INVALID_MESSAGE, INVALID_PRODUCT_CODE
from custom.ilsgateway.tanzania.handlers.keyword import KeywordHandler
from custom.ewsghana.alerts.alerts import report_completion_check, stock_alerts
from corehq.apps.sms.api import send_sms_to_verified_number
from corehq.apps.commtrack.sms import *


class ProductCodeException(Exception):
    pass


class EWSFormatter(object):

    REC_SEPARATOR = '-'

    def _clean_string(self, string):
        if not string:
            return string
        mylist = list(string)
        newstring = string[0]
        i = 1
        while i < len(mylist)-1:
            if mylist[i] == ' ' and mylist[i-1].isdigit() and mylist[i+1].isdigit():
                newstring += self.REC_SEPARATOR
            else:
                newstring = newstring + mylist[i]
            i += 1
        newstring = newstring + string[-1]
        string = newstring

        string = string.replace(' ', '')
        separators = [',', '/', ';', '*', '+', '-']
        for mark in separators:
            string = string.replace(mark, self.REC_SEPARATOR)
        junk = ['\'', '\"', '`', '(', ')']
        for mark in junk:
            string = string.replace(mark, '')
        return string.lower()

    def _getTokens(self, string):
        mylist = list(string)
        token = ''
        i = 0
        while i < len(mylist):
            token = token + mylist[i]
            if i+1 == len(mylist):
                # you've reached the end
                yield token
            elif mylist[i].isdigit() and not mylist[i+1].isdigit() or \
              mylist[i].isalpha() and not mylist[i+1].isalpha() or \
              not mylist[i].isalnum() and mylist[i+1].isalnum():
                yield token
                token = ''
            i += 1

    def format(self, string):
        """
        Old parse method, used in Ghana for more 'interesting' parsing.
        """
        if not string:
            return
        match = re.search("[0-9]", string)
        if not match:
            return string
        string = self._clean_string(string)
        an_iter = self._getTokens(string)
        commodity = None
        valid = False

        result = ''

        while True:
            try:
                while commodity is None or not commodity.isalpha():
                    commodity = an_iter.next().lower()
                count = an_iter.next()
                while not count.isdigit():
                    count = an_iter.next()
                result += '{} {}'.format(commodity, count)
                valid = True
                token_a = an_iter.next()
                if not token_a.isalnum():
                    token_b = an_iter.next()
                    while not token_b.isalnum():
                        token_b = an_iter.next()
                    if token_b.isdigit():
                        # if digit, then the user is reporting receipts
                        result += '.{} '.format(token_b)
                        commodity = None
                        valid = True
                    else:
                        # if alpha, user is reporting soh, so loop
                        commodity = token_b
                        valid = True
                else:
                    commodity = token_a
                    valid = True
            except ValueError, e:
                commodity = None
                continue
            except StopIteration:
                break
        if not valid:
            return string
        return result.strip()


class EWSStockAndReceiptParser(StockAndReceiptParser):

    def product_from_code(self, prod_code):
        try:
            return super(EWSStockAndReceiptParser, self).product_from_code(prod_code)
        except SMSError:
            raise ProductCodeException(unicode(INVALID_PRODUCT_CODE % prod_code))


class AlertsHandler(KeywordHandler):

    def handle(self):
        verified_contact = self.verified_contact
        user = verified_contact.owner
        domain = Domain.get_by_name(verified_contact.domain)
        split_text = self.msg.text.split(' ', 1)
        if split_text[0].lower() == 'soh':
            text = split_text[1]
        elif split_text[0].startswith('soh'):
            text = split_text[0][3:]
        else:
            text = self.msg.text

        if not domain.commtrack_enabled:
            return False
        try:
            data = EWSStockAndReceiptParser(domain, verified_contact).parse(EWSFormatter().format(text))
            if not data:
                return False
        except NotAUserClassError:
            return False
        except SMSError:
            send_sms_to_verified_number(verified_contact, unicode(INVALID_MESSAGE))
            return True
        except ProductCodeException as e:
            send_sms_to_verified_number(verified_contact, e.message)
            return True
        except Exception, e:  # todo: should we only trap SMSErrors?
            if settings.UNIT_TESTING or settings.DEBUG:
                raise
            send_sms_to_verified_number(verified_contact, 'problem with stock report: %s' % str(e))
            return True
        process(domain.name, data)
        transactions = data['transactions']
        stock_alerts(transactions, user)
        return True
