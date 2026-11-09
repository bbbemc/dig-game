from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_SECTION
from pathlib import Path

OUT = Path('/Users/nine/Documents/year1/Python/dig-game/output/pdf/python_exam_cheatsheet_source.docx')
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Mm(210), Mm(297)
sec.top_margin, sec.bottom_margin = Mm(12), Mm(10)
sec.left_margin, sec.right_margin = Mm(11), Mm(11)
sec.header_distance, sec.footer_distance = Mm(5), Mm(5)

NAVY = '18324B'
TEAL = '087E8B'
MUTED = '536579'
PALE = 'EFF4F7'

def set_cell_margins(cell, top=50, start=80, bottom=40, end=80):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in('w:tcMar')
    if tcMar is None:
        tcMar = OxmlElement('w:tcMar')
        tcPr.append(tcMar)
    for m, v in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = tcMar.find(qn('w:' + m))
        if node is None:
            node = OxmlElement('w:' + m)
            tcMar.append(node)
        node.set(qn('w:w'), str(v))
        node.set(qn('w:type'), 'dxa')

def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)

def font_run(run, size=8, bold=False, color='17212B', name='Thonburi'):
    run.font.name = name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)

def paragraph(container, text='', kind='body'):
    p = container.add_paragraph() if hasattr(container, 'add_paragraph') else None
    if kind == 'head':
        p.paragraph_format.space_before = Pt(5)
        p.paragraph_format.space_after = Pt(1.5)
        r = p.add_run(text)
        font_run(r, 10, True, TEAL)
    elif kind == 'code':
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Mm(1)
        p.paragraph_format.right_indent = Mm(1)
        p.paragraph_format.line_spacing = 1.0
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), PALE); pPr.append(shd)
        r = p.add_run(text)
        font_run(r, 6.6, False, '152A3A', 'Menlo')
    elif kind == 'small':
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(text)
        font_run(r, 7, False, MUTED)
    elif kind == 'bullet':
        p.paragraph_format.left_indent = Mm(2)
        p.paragraph_format.first_line_indent = Mm(-2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run('- ' + text)
        font_run(r, 7.7, False)
    else:
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(text)
        font_run(r, 7.7, False)
    return p

def clear_cell(cell):
    cell.text = ''
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)

def make_page(title, subtitle, left_items, right_items, label):
    header = doc.add_paragraph()
    header.paragraph_format.space_after = Pt(1)
    r = header.add_run(title); font_run(r, 17, True, NAVY)
    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(5)
    r = sub.add_run(subtitle); font_run(r, 8, False, MUTED)
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Mm(92)
    table.columns[1].width = Mm(92)
    for cell in table.rows[0].cells:
        cell.width = Mm(92)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        set_cell_margins(cell)
        clear_cell(cell)
    for cell, items in zip(table.rows[0].cells, [left_items, right_items]):
        for kind, txt in items:
            paragraph(cell, txt, kind)
    foot = doc.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    foot.paragraph_format.space_before = Pt(3)
    r = foot.add_run(label); font_run(r, 7, False, MUTED)

front_left = [
('head','วิธีเริ่มโจทย์ทุกข้อ'),
('bullet','ขีดเส้นใต้ input → output → เงื่อนไขพิเศษ แล้วจดชนิดข้อมูลที่จะคืน เช่น dict, list, int หรือ str.'),
('bullet','ถ้า assert ตรวจค่าที่เรียกกลับมา ให้ใช้ return; ใช้ print เมื่อโจทย์สั่งแสดงผล.'),
('bullet','แบ่งงานเป็น เตรียมผลลัพธ์ → วนข้อมูล → อัปเดต → return แล้วลองตัวอย่างเล็ก ๆ.'),
('head','Dictionary: เลือก key และ value'),
('code',"# รหัสวิชา -> (ชื่อ, หน่วยกิต)\ncourses = {'2301117': ('Calculus I', '4')}\ninfo = courses.get(course_id)\nif info is None: return 'Unknown'\nreturn info[0] + ' ' + info[1]"),
('bullet','อ่านค่า: d[key] หรือ d.get(key); เช็ก key: if key in d. รหัสที่มีศูนย์นำหน้าควรเก็บเป็น str.'),
('head','อ่านไฟล์และนับคำ'),
('code',"counts = {}\nwith open(file_name) as f:\n    for line in f:\n        for word in line.split():\n            word = word.strip(':?,.')\n            counts[word] = counts.get(word, 0) + 1\nreturn counts"),
('bullet','split() แบ่งตามช่องว่าง; strip(chars) ตัดอักขระที่หัวและท้ายคำ ไม่ได้ตัดเครื่องหมายกลางคำ.'),
('head','อ่านไฟล์: ชื่อกับคะแนน'),
('code',"scores = {}\nwith open(file_name) as f:\n    for line in f:\n        name, score = line.split()\n        scores[name] = int(score)\nreturn scores\n\n# เรียงคะแนนสูง -> ต่ำ\nreturn sorted(scores, key=scores.get, reverse=True)"),
('bullet','แปลงคะแนน/จำนวนเป็น int. sorted(..., key=..., reverse=True) เรียงตามค่าที่เลือก.'),
('head','Top 3 / เงื่อนไข / ผลรวม'),
('code',"top3 = sorted(scores, key=scores.get, reverse=True)[:3]\npopular = [name for name, n in sports.items() if n >= 15]\ntotal = sum(sports.values())"),
('bullet','รวมคะแนนหลายช่อง: total = int(a) + int(b) + int(c) + int(audience).')]

front_right = [
('head','Dictionary ซ้อน: stock / menu / ค่าเทอม'),
('code',"# stock[id][size] = quantity\nif product_id not in stock:\n    stock[product_id] = {}\nstock[product_id][size] = stock[product_id].get(size, 0) + qty\n\n# menu[drink][size] = price\ntotal = menu[drink][size] * number"),
('bullet','ไล่ชั้นจากนอกเข้าใน: key แรกคืออะไร? value เป็น dict แบบไหน? id อาจเป็น int แต่ size เป็น str.'),
('head','รับ input และตรวจเงื่อนไข'),
('code',"drink, size, number = input('...').split()\nnumber = int(number)\nif drink not in menu:\n    print('Drink not available.')\nelif size not in menu[drink]:\n    print('Incorrect size.')\nelse:\n    print(f'Total : {menu[drink][size] * number}')"),
('bullet','ตรวจชื่อเครื่องดื่มก่อน แล้วตรวจขนาดในเมนูนั้น. ใช้ราคาจากตารางในโจทย์ อย่าเดา.'),
('head','แยกกลุ่มจากรหัสนิสิต'),
('code',"faculty = student_id[-2:]  # 2 หลักท้าย\nlevel_digit = student_id[2]  # หลักที่ 3\nyear = int(student_id[:2])\n# map เป็น group / level / term / id_group\nfee = table[group][level][term][id_group]"),
('bullet','เก็บรหัสเป็น string เพื่อ slice. สร้าง dict ซ้อนตามโจทย์ แล้ว lookup ทีละชั้น.'),
('head','เช็กก่อนส่ง'),
('bullet','ชื่อตัวแปรตรงกัน, แปลง int ครบ, handle กรณีไม่พบ/ลิสต์ว่าง, คืนชนิดตามโจทย์.'),
('bullet','assert เทียบข้อความแบบตรงตัว: ช่องว่าง, colon, newline และบรรทัดว่างก็สำคัญ.'),
('bullet','อย่าลบ key จาก dict ระหว่างวน values; เก็บ key ที่จะลบก่อน.'),
('head','แปลโจทย์เป็นงานย่อย'),
('code',"ไฟล์ -> split/แปลงชนิด -> dict\ndict -> loop/เงื่อนไข -> list หรือผลรวม\ninput -> ตรวจข้อมูล -> lookup -> print"),
('small','โจทย์ในชุด: รายวิชา, นับคำ, จัดอันดับ, เครื่องดื่ม, stock, ค่าเทอม, คะแนนประกวด, กีฬาและจำนวนผู้เล่น')]

back_left = [
('head','คิดจากสิ่งของจริง'),
('bullet','หา noun ที่เป็นสิ่งของ → class. ข้อมูลที่มี → attribute. สิ่งที่ทำได้ → method.'),
('bullet','Class = แบบ; object = ของที่สร้างจากแบบ. self คือ object ที่กำลังเรียก method.'),
('code',"class Rectangle:\n    def __init__(self, length, width):\n        self.length = length\n        self.width = width\n    def area(self):\n        return self.length * self.width\n\nr = Rectangle(5, 3)\nr.area()  # self คือ r"),
('head','__init__ และการส่งข้อมูล'),
('bullet','Rectangle(5, 3) สร้าง object แล้วเรียก __init__(object, 5, 3) อัตโนมัติ; เก็บค่าด้วย self.attribute = parameter.'),
('bullet','obj.method(x) เทียบแนวคิดได้กับ Class.method(obj, x); ไม่ต้องส่ง self เอง.'),
('head','คลาสหนึ่งเก็บวัตถุอีกคลาส'),
('code',"class Book:\n    def __init__(self, title, author):\n        self.title = title\n        self.author = author  # object Author\n\n# author.name คือข้อมูลของ Author\n# book.title คือข้อมูลของ Book"),
('bullet','เส้นทางข้อมูล: book → book.author → book.author.name. ถ้าเก็บ object ใช้ .attribute ไม่ใช่ [0].')]

back_right = [
('head','รายการสินค้า / ตะกร้า'),
('code',"# cart[item] เก็บจำนวน\nself.cart[item] = self.cart.get(item, 0) + qty\nself.cart[item] -= qty\nif self.cart[item] <= 0:\n    del self.cart[item]\nreturn sum(self.cart.values())"),
('head','Bank + Account'),
('code',"# Bank.accounts: name -> Account object\nself.accounts[name] = Account(balance)\nself.accounts[src].withdraw(amount)\nself.accounts[dst].deposit(amount)\n\nfor name, account in self.accounts.items():\n    if account.get_balance() < 0:\n        debtors.append(name)"),
('bullet','accounts[name] คือ object Account; เรียก get_balance() เพื่ออ่านยอดที่ซ่อนใน __balance.'),
('code',"# rate = 1.5 หมายถึง 1.5%\ninterest = balance * rate / 100\nif interest >= 0: account.deposit(interest)\nelse: account.withdraw(-interest)"),
('head','Team: list ของ Member objects'),
('code',"for member in self.members:\n    if member.name == name:\n        self.members.remove(member)\n        break\n\ncounts = {}\nfor member in self.members:\n    counts[member.role] = counts.get(member.role, 0) + 1\ntotal = sum(counts.values())\npct = {role: round(n / total * 100, 2)\n       for role, n in counts.items()}"),
('bullet','members เก็บ object Member: อ่าน member.name / member.role. remove(name) ใช้ไม่ได้ เพราะ name เป็น str.'),
('head','Library: dict ของ Book objects'),
('code',"# ISBN -> Book object\nif book.isbn in self.books:\n    self.books[book.isbn].available_copies += book.available_copies\nelse:\n    self.books[book.isbn] = book\n\ntotal = sum(b.available_copies for b in self.books.values())\nfound = [b for b in self.books.values()\n         if b.author.name == author_name]"),
('head','__str__ และข้อความตรงเป๊ะ'),
('code',"def __str__(self):\n    return f'Name: {self.name}, Role: {self.role}'\n\n# print(obj) เรียก __str__ อัตโนมัติ\n# display method: return ไม่ใช่ print\n# \\n คือขึ้นบรรทัดใหม่"),
('bullet','ถ้า assert เทียบ string เช็ก newline ท้ายข้อความ/บรรทัดว่าง. ผิดช่องว่างเดียวก็ fail.'),
('head','Checklist OOP'),
('bullet','กำหนด attribute ใน __init__; ใช้ self เมื่ออ่านหรือแก้ข้อมูลของ object.'),
('bullet','คลาสหนึ่งเก็บ object อีกคลาสได้ (has-a). ถ้ารับ object ที่สร้างไว้แล้วมาเก็บ ก็ส่งต่อ reference เดิม.'),
('bullet','ถ้าโจทย์ว่า returns ต้อง return. อัปเดตจำนวนก่อนคืนผล และเช็กกรณี 0 / ไม่พบ.'),
('small','ลำดับทำข้อสอบ: ระบุชนิดข้อมูล → เขียน __init__ → ทำ method ทีละตัว → ทดลอง → เทียบ return กับ test')]

make_page('ชีตสรุป Python ก่อนสอบ', 'ด้านหน้า • Lab 6–7 • ฟังก์ชัน, dictionary, ไฟล์ และ input', front_left, front_right, 'หน้า 1 • ฟังก์ชันและข้อมูล')
doc.add_page_break()
make_page('OOP: มองข้อมูลเป็นวัตถุ', 'ด้านหลัง • Lab 8 • คลาส, attribute, method และ object collection', back_left, back_right, 'หน้า 2 • OOP และคลาส')
doc.save(OUT)
print(OUT)
