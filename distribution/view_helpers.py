from decimal import *
import datetime
from operator import attrgetter


from django.forms.formsets import formset_factory

from models import *
from forms import *

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def weekly_production_plans(week_date):
    monday = week_date - datetime.timedelta(days=datetime.date.weekday(week_date))
    saturday = monday + datetime.timedelta(days=5)
    plans = ProductPlan.objects.select_related(depth=1).filter(
        role="producer",
        from_date__lte=week_date, 
        to_date__gte=saturday)
    for plan in plans:
        plan.category = plan.product.parent_string()
        plan.product_name = plan.product.short_name
    plans = sorted(plans, key=attrgetter('category',
                                            'product_name'))
    return plans

def plan_columns(from_date, to_date):
    columns = []
    wkdate = from_date
    while wkdate <= to_date:
        columns.append(wkdate.strftime('%Y-%m-%d'))
        wkdate = wkdate + datetime.timedelta(days=7)
    return columns

def sd_columns(from_date, to_date):
    columns = []
    wkdate = from_date
    while wkdate <= to_date:
        columns.append(wkdate.strftime('%Y_%m_%d'))
        wkdate = wkdate + datetime.timedelta(days=7)
    return columns


# shd plan_weeks go to the view and include headings?
# somebody needs headings!
def create_weekly_plan_forms(rows, data=None):
    form_list = []
    PlanCellFormSet = formset_factory(PlanCellForm, extra=0)

    for row in rows:
        product = row[0]
        row_form = PlanRowForm(data, prefix=product.id, initial={'product_id': product.id})
        row_form.product = product.long_name
        cells = row[1:len(row)]
        initial_data = []
        for cell in cells:
            plan_id = ""
            if cell.plan:
                plan_id = cell.plan.id
            dict = {
                'plan_id': plan_id,
                'product_id': cell.product.id,
                'from_date': cell.from_date,
                'to_date': cell.to_date,
                'quantity': cell.quantity,
            }
            initial_data.append(dict)
        row_form.formset = PlanCellFormSet(data, prefix=product.id, initial=initial_data)
        form_list.append(row_form)
    return form_list
        

class SupplyDemandTable(object):
    def __init__(self, columns, rows):
         self.columns = columns
         self.rows = rows

def supply_demand_table(from_date, to_date, member=None):
    plans = ProductPlan.objects.all()
    cps = ProducerProduct.objects.filter(
        inventoried=False,
        default_avail_qty__gt=0,
    )
    constants = {}
    for cp in cps:
        constants.setdefault(cp.product, Decimal("0"))
        constants[cp.product] += cp.default_avail_qty
    if member:
        plans = plans.filter(member=member)
    rows = {}    
    for plan in plans:
        wkdate = from_date
        product = plan.product.supply_demand_product()
        constant = Decimal('0')
        cp = constants.get(product)
        if cp:
            constant = cp
        row = []
        while wkdate <= to_date:
            row.append(constant)
            wkdate = wkdate + datetime.timedelta(days=7)
        row.insert(0, product)
        rows.setdefault(product, row)
        wkdate = from_date
        week = 0
        while wkdate <= to_date:
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                if plan.role == "producer":
                    rows[product][week + 1] += plan.quantity
                else:
                    rows[product][week + 1] -= plan.quantity
            wkdate = wkdate + datetime.timedelta(days=7)
            week += 1
    label = "Product/Weeks"
    columns = [label]
    wkdate = from_date
    while wkdate <= to_date:
        columns.append(wkdate)
        wkdate = wkdate + datetime.timedelta(days=7)
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x[0].short_name, y[0].short_name))
    sdtable = SupplyDemandTable(columns, rows)
    return sdtable

def supply_demand_rows(from_date, to_date, member=None):
    plans = ProductPlan.objects.select_related(depth=1).all()
    cps = ProducerProduct.objects.filter(
        inventoried=False,
        default_avail_qty__gt=0,
    )
    constants = {}
    for cp in cps:
        constants.setdefault(cp.product, Decimal("0"))
        constants[cp.product] += cp.default_avail_qty
    if member:
        plans = plans.filter(member=member)
    rows = {}
    #todo: 
    # spread storage items over many weeks
    # if plan.product expiration_days > 1 week:
    # spread remainder over weeks until consumed or expired.
    # means plannable parents cd determine expiration.
    # may require another pass thru storage plans...
    for plan in plans:
        wkdate = from_date
        #this is slow:
        #product = plan.product.supply_demand_product()
        product = plan.product
        #constant = Decimal('0')
        constant = ""
        cp = constants.get(product)
        if cp:
            constant = str(cp)
        row = {}
        while wkdate <= to_date:
            row[wkdate.strftime('%Y_%m_%d')] = str(constant)
            wkdate = wkdate + datetime.timedelta(days=7)
        row["product"] =  product.long_name
        row["id"] = product.id
        rows.setdefault(product, row)
        wkdate = from_date
        while wkdate <= to_date:
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                key = wkdate.strftime('%Y_%m_%d')
                value = rows[product][key]
                if value == "":
                    value = Decimal("0")
                else:
                    value = Decimal(value)
                if plan.role == "producer":
                    value += plan.quantity
                else:
                    value -= plan.quantity
                rows[product][key] = str(value)
            wkdate = wkdate + datetime.timedelta(days=7)
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x["product"], y["product"]))
    return rows

def supply_demand_weekly_table(week_date):
    plans = ProductPlan.objects.filter(
        from_date__lte=week_date,
        to_date__gte=week_date,
    ).order_by("-role", "member__short_name")
    columns = []
    rows = {}
    for plan in plans:
        if not plan.member in columns:
            columns.append(plan.member)
    columns.insert(0, "Product\Member")
    columns.append("Balance")
    for plan in plans:
        if not rows.get(plan.product):
            row = []
            for i in range(0, len(columns)-1):
                row.append(Decimal("0"))
            row.insert(0, plan.product)
            rows[plan.product] = row
        if plan.role == "producer":
            rows[plan.product][columns.index(plan.member)] += plan.quantity
            rows[plan.product][len(columns)-1] += plan.quantity
        else:
            rows[plan.product][columns.index(plan.member)] -= plan.quantity
            rows[plan.product][len(columns)-1] -= plan.quantity
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x[0].short_name, y[0].short_name))
    sdtable = SupplyDemandTable(columns, rows)
    return sdtable

def dojo_supply_demand_weekly_table(week_date):
    plans = ProductPlan.objects.filter(
        from_date__lte=week_date,
        to_date__gte=week_date,
    ).order_by("-role", "member__short_name")
    # for columns: product, member.short_name(s), balance
    # but only members are needed here...product and balance can be added in
    # template 
    # for rows: dictionaries with the above keys
    columns = []
    rows = {}
    for plan in plans:
        if not plan.member.short_name in columns:
            columns.append(plan.member.short_name)
    #columns.insert(0, "Product\Member")
    columns.append("Balance")
    for plan in plans:
        if not rows.get(plan.product):
            row = {}
            for column in columns:
                row[column] = 0
            row["product"] = plan.product.long_name
            row["id"] = plan.product.id
            row["Balance"] = 0
            rows[plan.product] = row
        if plan.role == "producer":
            rows[plan.product][plan.member.short_name] += int(plan.quantity)
            rows[plan.product]["Balance"] += int(plan.quantity)
        else:
            rows[plan.product][plan.member.short_name] -= int(plan.quantity)
            rows[plan.product]["Balance"] -= int(plan.quantity)
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x["product"], y["product"]))
    sdtable = SupplyDemandTable(columns, rows)
    return sdtable

class SuppliableDemandCell(object):
    def __init__(self, supply, demand):
         self.supply = supply
         self.demand = demand

    def suppliable(self):
        answer = Decimal("0")
        if self.supply and self.demand:
            if self.supply > self.demand:
                answer = self.demand
            else:
                answer = self.supply
        return answer

def suppliable_demand(from_date, to_date, member=None):
    plans = ProductPlan.objects.all()
    if member:
        plans = plans.filter(member=member)
    rows = {}    
    for plan in plans:
        wkdate = from_date
        row = []
        while wkdate <= to_date:
            row.append(SuppliableDemandCell(Decimal("0"), Decimal("0")))
            wkdate = wkdate + datetime.timedelta(days=7)
        product = plan.product.supply_demand_product()

        row.insert(0, product)
        rows.setdefault(product, row)
        wkdate = from_date
        week = 0
        while wkdate <= to_date:
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                if plan.role == "producer":
                    rows[product][week + 1].supply += plan.quantity
                else:
                    rows[product][week + 1].demand += plan.quantity
            wkdate = wkdate + datetime.timedelta(days=7)
            week += 1
    rows = rows.values()
    cust_fee = customer_fee()
    for row in rows:
        for x in range(1, len(row)):
            sd = row[x].suppliable()
            if sd >= 0:
                income = sd * row[0].price
                row[x] = income
            else:
                row[x] = Decimal("0")
    income_rows = []
    for row in rows:
        base = Decimal("0")
        total = Decimal("0")
        for x in range(1, len(row)):
            cell = row[x]
            base += cell
            cell += cell * cust_fee
            total += cell
            row[x] = cell.quantize(Decimal('.1'), rounding=ROUND_UP)            
        if total:
            net = base * cust_fee + (base * producer_fee())
            net = net.quantize(Decimal('1.'), rounding=ROUND_UP)
            total = total.quantize(Decimal('1.'), rounding=ROUND_UP)
            row.append(total)
            row.append(net)
            income_rows.append(row)
    label = "Item\Weeks"
    columns = [label]
    wkdate = from_date
    while wkdate <= to_date:
        columns.append(wkdate)
        wkdate = wkdate + datetime.timedelta(days=7)
    columns.append("Total")
    columns.append("Net")
    income_rows.sort(lambda x, y: cmp(x[0].long_name, y[0].short_name))
    sdtable = SupplyDemandTable(columns, income_rows)
    return sdtable

def json_income_rows(from_date, to_date, member=None):
    plans = ProductPlan.objects.all()
    if member:
        plans = plans.filter(member=member)
    rows = {}    
    for plan in plans:
        wkdate = from_date
        row = {}
        while wkdate <= to_date:
            row[wkdate.strftime('%Y_%m_%d')] = SuppliableDemandCell(Decimal("0"), Decimal("0"))
            wkdate = wkdate + datetime.timedelta(days=7)
        product = plan.product.supply_demand_product()
        row["product"] =  product.long_name
        row["id"] = product.id
        row["price"] = product.price
        rows.setdefault(product, row)
        wkdate = from_date
        while wkdate <= to_date:
            key = wkdate.strftime('%Y_%m_%d')
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                if plan.role == "producer":
                    rows[product][key].supply += plan.quantity
                else:
                    rows[product][key].demand += plan.quantity
            wkdate = wkdate + datetime.timedelta(days=7)
    rows = rows.values()
    cust_fee = customer_fee()
    #import pdb; pdb.set_trace()
    for row in rows:
        wkdate = from_date
        while wkdate <= to_date:
            key = wkdate.strftime('%Y_%m_%d')
            sd = row[key].suppliable()
            if sd > 0:
                income = sd * row["price"]
                row[key] = income
            else:
                row[key] = Decimal("0")
            wkdate = wkdate + datetime.timedelta(days=7)
    income_rows = []
    for row in rows:
        base = Decimal("0")
        total = Decimal("0")
        wkdate = from_date
        while wkdate <= to_date:
            key = wkdate.strftime('%Y_%m_%d')
            cell = row[key]
            base += cell
            cell += cell * cust_fee
            total += cell
            row[key] = str(cell.quantize(Decimal('.1'), rounding=ROUND_UP))
            wkdate = wkdate + datetime.timedelta(days=7)
        if total:
            net = base * cust_fee + (base * producer_fee())
            net = net.quantize(Decimal('1.'), rounding=ROUND_UP)
            total = total.quantize(Decimal('1.'), rounding=ROUND_UP)
            row["total"] = str(total)
            row["net"] = str(net)
            row["price"] = str(row["price"])
            income_rows.append(row)
    income_rows.sort(lambda x, y: cmp(x["product"], y["product"]))
    return income_rows


class PlannedWeek(object):
    def __init__(self, product, from_date, to_date, quantity):
         self.product = product
         self.from_date = from_date
         self.to_date = to_date
         self.quantity = quantity
         self.plan = None

def plan_weeks(member, products, from_date, to_date):
    plans = ProductPlan.objects.filter(member=member)
    #if member.is_customer():
    #    products = CustomerProduct.objects.filter(customer=member, planned=True)
    #else:
    #    products = ProducerProduct.objects.filter(producer=member, planned=True)
    #if not products:
    #    products = Product.objects.filter(plannable=True)
    rows = {}    
    for pp in products:
        try:
            product = pp.product
        except:
            product = pp
        wkdate = from_date
        row = [product]
        while wkdate <= to_date:
            enddate = wkdate + datetime.timedelta(days=6)
            row.append(PlannedWeek(product, wkdate, enddate, Decimal("0")))
            wkdate = enddate + datetime.timedelta(days=1)
        #row.insert(0, product)
        rows.setdefault(product, row)
    for plan in plans:
        product = plan.product
        wkdate = from_date
        week = 0
        while wkdate <= to_date:
            enddate = wkdate + datetime.timedelta(days=6)
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                rows[product][week + 1].quantity = plan.quantity
                rows[product][week + 1].plan = plan
            wkdate = wkdate + datetime.timedelta(days=7)
            week += 1
    label = "Product/Weeks"
    columns = [label]
    wkdate = from_date
    while wkdate <= to_date:
        columns.append(wkdate)
        wkdate = wkdate + datetime.timedelta(days=7)
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x[0].short_name, y[0].short_name))
    sdtable = SupplyDemandTable(columns, rows)
    return sdtable

def plans_for_dojo(member, products, from_date, to_date):
    #import pdb; pdb.set_trace()
    plans = ProductPlan.objects.filter(member=member)
    rows = {}    
    for pp in products:
        yearly = "0"
        try:
            product = pp.product
            yearly = str(pp.default_quantity)
        except:
            product = pp
        wkdate = from_date
        row = {}
        row["product"] = product.long_name
        row["yearly"] = yearly
        row["id"] = product.id
        row["member_id"] = member.id
        row["from_date"] = from_date.strftime('%Y-%m-%d')
        row["to_date"] = to_date.strftime('%Y-%m-%d')
        while wkdate <= to_date:
            enddate = wkdate + datetime.timedelta(days=6)
            row[wkdate.strftime('%Y-%m-%d')] = "0"
            wkdate = enddate + datetime.timedelta(days=1)
        rows.setdefault(product, row)
    #import pdb; pdb.set_trace()
    for plan in plans:
        product = plan.product
        wkdate = from_date
        week = 0
        while wkdate <= to_date:
            enddate = wkdate + datetime.timedelta(days=6)
            if plan.from_date <= wkdate and plan.to_date >= wkdate:
                rows[product][wkdate.strftime('%Y-%m-%d')] = str(plan.quantity)
                rows[product][":".join([wkdate.strftime('%Y-%m-%d'), "plan_id"])] = plan.id
            wkdate = wkdate + datetime.timedelta(days=7)
            week += 1
    rows = rows.values()
    rows.sort(lambda x, y: cmp(x["product"], y["product"]))
    return rows

def create_all_inventory_item_forms(avail_date, plans, items, data=None):
    item_dict = {}
    for item in items:
        # This means one lot per producer per product per week
        item_dict["-".join([str(item.product.id), str(item.producer.id)])] = item
    form_list = []
    for plan in plans:
        #import pdb; pdb.set_trace()
        custodian_id = ""
        try:
            member = plan.member
        except:
            member = plan.producer
        try:
            item = item_dict["-".join([str(plan.product.id),
                                       str(member.id)])]
            if item.custodian:
                custodian_id = item.custodian.id
        except KeyError:
            item = False
        try:
            plan_qty = plan.quantity
        except:
            plan_qty = 0
        #import pdb; pdb.set_trace()
        if item:
            pref = "-".join(["item", str(item.id)])
            the_form = AllInventoryItemForm(data, prefix=pref, initial={
                'item_id': item.id,
                'product_id': item.product.id,
                'producer_id': item.producer.id,
                'freeform_lot_id': item.freeform_lot_id,
                'field_id': item.field_id,
                'custodian': custodian_id,
                'inventory_date': item.inventory_date,
                'planned': item.planned,
                'received': item.received,
                'notes': item.notes})
        else:
            pref = "-".join(["plan", str(plan.id)])
            the_form = AllInventoryItemForm(data, prefix=pref, initial={
                'item_id': 0,
                'product_id': plan.product.id,
                'producer_id': member.id,
                'inventory_date': avail_date,
                'planned': 0,
                'received': 0,
                'notes': ''})
        the_form.description = plan.product.long_name
        the_form.producer = member.short_name
        the_form.plan_qty = plan_qty
        form_list.append(the_form)
    #import pdb; pdb.set_trace()
    #form_list.sort(lambda x, y: cmp(x.producer, y.producer))
    form_list = sorted(form_list, key=attrgetter('producer', 'description'))
    return form_list 


