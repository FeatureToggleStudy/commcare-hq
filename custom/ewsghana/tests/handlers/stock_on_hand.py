from custom.ewsghana.tests.handlers.utils import EWSScriptTest, restore_location_products, \
    assign_products_to_location


class StockOnHandTest(EWSScriptTest):

    def test_stock_on_hand(self):
        a = """
           5551234 > soh lf 10.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > soh lf 10.0 mc 20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > SOH LF 10.0 MC 20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_stockout(self):
        a = """
           5551234 > soh lf 0.0 mc 0.0
           5551234 < Dear {}, these items are stocked out: lf mc. Please order lf 15 mc 24.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_stockout_no_consumption(self):
        a = """
           5551234 > soh ng 0.0
           5551234 < Dear {}, these items are stocked out: ng.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_low_supply(self):
        a = """
           5551234 > soh lf 7.0 mc 9.0
           5551234 < Dear {}, these items need to be reordered: lf mc. Please order lf 8 mc 15.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_low_supply_no_consumption(self):
        a = """
           5551234 > soh ng 3.0
           5551234 < Dear {}, thank you for reporting the commodities you have in stock.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_over_supply(self):
        a = """
            5551234 > soh lf 30.0 mc 40.0
            5551234 < Dear {}, these items are overstocked: lf mc. The district admin has been informed.
        """.format(self.user1.full_name)
        self.run_script(a)

    def test_soh_and_receipt(self):
        a = """
           5551234 > soh lf 10.20 mc 20.0
           5551234 < Dear {}, thank you for reporting the commodities you have. You received lf 20.
           """.format(self.user1.full_name)
        self.run_script(a)

    def test_combined1(self):
        second_message = "Dear {}, Test Facility is experiencing the following problems: stockouts Lofem; " \
                         "below reorder level Male Condom".format(self.user2.full_name)
        last_message = "Dear {}, these items are stocked out: lf. these items need to be reordered: mc. " \
                       "Please order lf 30 mc 29.".format(self.user3.full_name)
        a = """
           333333 > soh lf 0.0 mc 1.0
           222222  < %s
           333333 < %s
           """ % (second_message, last_message)
        self.run_script(a)

    def test_combined2(self):
        second_message = "Dear {}, Test Facility is experiencing the following problems: stockouts Male Condom; " \
                         "below reorder level Micro-G".format(self.user2.full_name)
        third_and_last_message = "Dear {}, these items are stocked out: mc. " \
                                 "these items need to be reordered: mg. Please " \
                                 "order mc 30 mg 29.".format(self.user3.full_name)
        fifth_message = "Dear {}, Test Facility is experiencing the following problems: stockouts Male Condom; " \
                        "below reorder level Micro-G; overstocked Lofem".format(self.user2.full_name)
        last_message = "Dear {}, these items are stocked out: mc. these items need to be reordered: mg. " \
                       "Please order mc 30 mg 29.".format(self.user3.full_name)
        a = """
           333333 > soh mc 0.0 mg 1.0
           222222 < %s
           333333 < %s
           333333 > soh mc 0.0 mg 1.0 lf 100.0
           222222 < %s
           333333 < %s
           """ % (second_message, third_and_last_message, fifth_message, last_message)
        self.run_script(a)

    def test_combined3(self):
        second_message = "Dear {}, Test Facility is experiencing the following problems: stockouts Male Condom; " \
                         "below reorder level Micro-G".format(self.user2.full_name)
        third_message = "Dear {}, these items are stocked out: mc. these items need to be reordered: mg. " \
                        "Please order mc 30 mg 29.".format(self.user3.full_name)
        fifth_message = "Dear {}, Test Facility is experiencing the following problems: " \
                        "stockouts Male Condom; below reorder level Micro-G".format(self.user2.full_name)
        last_message = "Dear {}, these items are stocked out: mc. these items need to be reordered: mg. " \
                       "Please order mc 30 mg 29.".format(self.user3.full_name)
        a = """
           333333 > soh mc 0.0 mg 1.0 ng 300.0
           222222 < %s
           333333 < %s
           333333 > soh mc 0.2 mg 1.0 ng 300.1
           222222 < %s
           333333 < %s
           """ % (second_message, third_message, fifth_message, last_message)
        self.run_script(a)

    def test_combined4(self):
        second_message = "Dear {}, Test Facility is experiencing the following problems: stockouts Male Condom; " \
                         "below reorder level Micro-G".format(self.user2.full_name)
        last_message = "Dear {}, these items are stocked out: mc. these items need to be reordered: mg. " \
                       "Please order mc 30 mg 29.".format(self.user3.full_name)
        a = """
           333333 > soh mc 0.0 mg 1.0 ng 300.4
           222222 < %s
           333333 < %s
           """ % (second_message, last_message)
        self.run_script(a)

    def test_combined5(self):
        a = """
           333333 > soh mc 16.0 lf 16.0 mg 300.0
           222222 < Dear {}, Test Facility is experiencing the following problems: overstocked Micro-G
           333333 < Dear {}, these items are overstocked: mg. The district admin has been informed.
           """.format(self.user2.full_name, self.user3.full_name)
        self.run_script(a)

    def test_incomplete_report(self):
        assign_products_to_location()
        a = """
            5551234 > soh mg 31.0
            5551234 < Dear {0}, still missing jd ng.
            5551234 > soh jd 25.0
            5551234 < Dear {0}, still missing ng.
            5551234 > soh ng 25.0
            5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
        """.format(self.user1.full_name)
        self.run_script(a)
        restore_location_products()

    def test_incomplete_report2(self):
        assign_products_to_location()
        a = """
            5551234 > soh mg 25.0 jd 25.0 ng 25.0
            5551234 < Dear {}, thank you for reporting the commodities you have in stock.
        """.format(self.user1.full_name)
        self.run_script(a)
        restore_location_products()

    def test_punctuation(self):
        a = """
           5551234 > soh lf 10.0 mc 20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > sohlf10.0mc20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > lf10.0mc20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > LF10.0MC 20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > LF10-1MC 20,3
           5551234 < Dear {0}, thank you for reporting the commodities you have. You received lf 1 mc 3.
           5551234 > LF(10.0), mc (20.0)
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > LF10.0-mc20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > LF10.0-mc20- 0
           5551234 < Dear {0}, thank you for reporting the commodities you have in stock.
           5551234 > LF10-3mc20 0
           5551234 < Dear {0}, thank you for reporting the commodities you have. You received lf 3.
           5551234 > LF10----3mc20.0
           5551234 < Dear {0}, thank you for reporting the commodities you have. You received lf 3.
           """.format(self.user1.full_name)
        self.run_script(a)
