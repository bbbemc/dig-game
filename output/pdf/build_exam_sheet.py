from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, FrameBreak
from pathlib import Path

OUT = Path('/Users/nine/Documents/year1/Python/dig-game/output/pdf/python_exam_cheatsheet_front_back.pdf')
pdfmetrics.registerFont(TTFont('Code', '/System/Library/Fonts/Menlo.ttc', subfontIndex=0))

navy = colors.HexColor('#18324B')
teal = colors.HexColor('#087E8B')
muted = colors.HexColor('#536579')
code_bg = colors.HexColor('#EFF4F7')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Title2', fontName='Helvetica-Bold', fontSize=18, leading=21,
                          textColor=navy, spaceAfter=2*mm))
styles.add(ParagraphStyle(name='Sub2', fontName='Helvetica', fontSize=8.7, leading=10.8,
                          textColor=muted, spaceAfter=3*mm))
styles.add(ParagraphStyle(name='Head2', fontName='Helvetica-Bold', fontSize=11.5, leading=13.8,
                          textColor=teal, spaceBefore=2*mm, spaceAfter=1.2*mm,
                          keepWithNext=True))
styles.add(ParagraphStyle(name='Body2', fontName='Helvetica', fontSize=9.2, leading=11.9,
                          textColor=colors.HexColor('#17212B'), spaceAfter=1.6*mm))
styles.add(ParagraphStyle(name='Code2', fontName='Code', fontSize=7.2, leading=9.1,
                          textColor=colors.HexColor('#152A3A'), backColor=code_bg,
                          borderPadding=3, leftIndent=2, rightIndent=2,
                          spaceBefore=0.5*mm, spaceAfter=1.3*mm))
styles.add(ParagraphStyle(name='Small2', fontName='Helvetica', fontSize=7.8, leading=9.8,
                          textColor=muted, spaceAfter=0.8*mm))

def P(text, style='Body2'):
    return Paragraph(text, styles[style])
def H(text): return P(text, 'Head2')
def C(text): return P(text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>'), 'Code2')
def B(text): return P('• ' + text)

class SheetDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm,
                         topMargin=13*mm, bottomMargin=10*mm, title='Python Exam Cheatsheet')
        w = (A4[0] - 24*mm - 6*mm) / 2
        h = A4[1] - 23*mm
        frames = [Frame(12*mm, 10*mm, w, h, leftPadding=0, rightPadding=3*mm,
                        topPadding=0, bottomPadding=0, id='left'),
                  Frame(12*mm + w + 6*mm, 10*mm, w, h, leftPadding=3*mm, rightPadding=0,
                        topPadding=0, bottomPadding=0, id='right')]
        self.addPageTemplates([PageTemplate(id='sheet', frames=frames, onPage=self.decorate)])
    def decorate(self, canvas, doc):
        canvas.saveState()
        page = canvas.getPageNumber()
        canvas.setFillColor(navy); canvas.setFont('Helvetica-Bold', 7.5)
        canvas.drawString(12*mm, A4[1]-8*mm, 'PYTHON  |  EXAM REVIEW')
        canvas.setFillColor(muted); canvas.setFont('Helvetica', 7)
        label = 'FRONT • FUNCTIONS & DATA' if page == 1 else 'BACK • OOP & WORKED EXAMPLE'
        canvas.drawRightString(A4[0]-12*mm, 6*mm, f'{label}  |  {page}/2')
        canvas.setStrokeColor(colors.HexColor('#D8E0E7')); canvas.setLineWidth(.5)
        canvas.line(A4[0]/2, 11*mm, A4[0]/2, A4[1]-11*mm)
        canvas.restoreState()

story = [
P('Python Exam Cheatsheet', 'Title2'),
P('Front • Labs 6–7 • Functions, dictionaries, files, input and tests', 'Sub2'),
H('A reliable way to start'),
B('Mark the input, required output, special cases, and exact return type (dict, list, int or str).'),
B('If an assert checks a returned value, use return. Use print only when the prompt asks for displayed output.'),
B('Build the result in four steps: initialize → loop → update → return. Trace one small example by hand.'),
H('Dictionary: choose key and value'),
C("# course_id -> (course_name, credits)\ncourses = {'2301117': ('Calculus I', '4')}\ninfo = courses.get(course_id)\nif info is None:\n    return 'Unknown'\nreturn info[0] + ' ' + info[1]"),
B('Read with d[key] or d.get(key); test membership with key in d. Keep IDs as strings when leading zeroes or slicing matter.'),
H('Read a file and count words'),
C("counts = {}\nwith open(file_name) as f:\n    for line in f:\n        for word in line.split():\n            word = word.strip(':?,.')\n            counts[word] = counts.get(word, 0) + 1\nreturn counts"),
B('split() separates on whitespace. strip(chars) removes those characters only from the beginning and end of each token.'),
H('Read name-score pairs and rank'),
C("scores = {}\nwith open(file_name) as f:\n    for line in f:\n        name, score = line.split()\n        scores[name] = int(score)\nreturn sorted(scores, key=scores.get, reverse=True)"),
B('Convert numeric text with int(). sorted(dict, key=dict.get, reverse=True) returns keys ordered by their values.'),
H('Top three, filters and totals'),
C("top3 = sorted(scores, key=scores.get, reverse=True)[:3]\npopular = [name for name, n in sports.items() if n >= 15]\ntotal = sum(sports.values())\nsports[sport] = sports.get(sport, 0) + players"),
B('Use accumulation when a name can appear on multiple file lines. The last line adds this row to the existing total.'),
H('Worked trace: contest scores'),
C("File row: S01 8 9 7 60\nTotal = 8 + 9 + 7 + 60 = 84\nscores['S01'] = 84\nRepeat for each row, then sort keys by score\nTop 3 = sorted(scores, key=scores.get,\n               reverse=True)[:3]"),
B('Separate parsing from ranking: get_dict builds the score dictionary; find_top3 only sorts that dictionary.'),
FrameBreak(),
P('Data patterns & checks', 'Title2'),
P('Front • Nested dictionaries, input validation and exact checks', 'Sub2'),
H('Nested dictionaries: stock and menu'),
C("# stock[product_id][size] = quantity\nif product_id not in stock:\n    stock[product_id] = {}\nstock[product_id][size] = stock[product_id].get(size, 0) + qty\n\n# menu[drink][size] = price\ntotal = menu[drink][size] * number"),
B('Read nested data from the outside in: first key → inner dictionary → second key → value. Match the required types (int ID, string size, etc.).'),
H('Mini trace: count word frequency'),
C("Line: 'Hi, Ana. Hi'\nsplit() -> ['Hi,', 'Ana.', 'Hi']\nstrip(':?,.') -> ['Hi', 'Ana', 'Hi']\ncount 'Hi' twice; count 'Ana' once\nResult: {'Hi': 2, 'Ana': 1}"),
B('At each token, ask: is it already a key? Add 1 if yes; otherwise start it at 1.'),
H('Input, then validate'),
C("drink, size, number = input('...').split()\nnumber = int(number)\nif drink not in menu:\n    print('Drink not available.')\nelif size not in menu[drink]:\n    print('Incorrect size.')\nelse:\n    print(f'Total : {menu[drink][size] * number}')"),
B('Check the drink before looking up its size. Use the price table from the prompt; do not guess values.'),
H('Trace one menu lookup'),
C("Input: Latte L 2\nmenu['Latte']['L'] -> 75\nnumber -> int('2') -> 2\ntotal = 75 * 2 -> 150\nOutput: Total : 150"),
B('A lowercase name can be a different key. Match the prompt’s capitalization and check invalid drink/size before indexing.'),
H('Student ID → tuition lookup'),
C("faculty = student_id[-2:]  # last 2 digits\nlevel_digit = student_id[2]  # third digit\nyear = int(student_id[:2])\nfee = table[group][level][term][id_group]"),
B('Third digit: 3/4 = Bachelor, 7 = Graduate. Terms 1/2 map to S1_2; term 3 maps to S3.'),
B('Year prefixes: 48–49 = ID_1, 50–55 = ID_2, 56+ = ID_3. Faculty group 1: 21, 23, 25, 28, 30–39, 53. Group 2: 22, 24, 26, 27, 29, 34, 40, 51.'),
H('Before submitting'),
B('Check capitalization, punctuation, spaces, and trailing newlines: string assertions compare every character.'),
B('Handle missing keys, empty lists, and zero counts. Do not delete dictionary keys while iterating over that dictionary.'),
PageBreak(),
P('OOP: Think in Objects', 'Title2'),
P('Back • Lab 8 • Classes, attributes, methods and object collections', 'Sub2'),
H('Start from real things'),
B('Nouns that represent things become classes. Their data becomes attributes; their actions become methods.'),
B('A class is a blueprint; an object is one instance. self means “this object,” the instance using the method.'),
C("class Rectangle:\n    def __init__(self, length, width):\n        self.length = length\n        self.width = width\n    def area(self):\n        return self.length * self.width\n    def perimeter(self):\n        return 2 * (self.length + self.width)\n\nr = Rectangle(5, 3)\nr.area()  # self is r"),
H('__init__ and how values move'),
B('Rectangle(5, 3) creates an object and calls __init__ automatically. Python passes that object as self; 5 and 3 become length and width.'),
B('Calling obj.method(x) is conceptually Class.method(obj, x). Do not pass self yourself.'),
H('Trace self in a call'),
C("r = Rectangle(5, 3)\nr.area()\n# same idea as Rectangle.area(r)\n# inside area: self is r\n# self.length is 5; self.width is 3\n# result returned: 15"),
H('One object can contain another'),
C("class Book:\n    def __init__(self, title, author):\n        self.title = title\n        self.author = author  # an Author object\n\nbook.author.name  # follow the reference to the name"),
B('Use dot access for object attributes. If book.author stores an Author object, read its name as book.author.name, not book.author[0].'),
H('Collection of objects'),
B('A list may hold Member objects: loop with for member in self.members, then read member.name or member.role.'),
B('A dictionary may map an ID to an object: self.books[book.isbn] = book. Later, self.books[isbn] is the Book object.'),
H('Bank and Team patterns'),
C("# name -> Account object\nself.accounts[name] = Account(balance)\nself.accounts[src].withdraw(amount)\nself.accounts[dst].deposit(amount)\n\n# list of Member objects\nfor member in self.members:\n    if member.name == name:\n        self.members.remove(member)\n        break"),
B('For role counts, use counts[member.role] = counts.get(member.role, 0) + 1. For a percentage, count / total * 100, then round(..., 2).'),
FrameBreak(),
P('Worked example: Library', 'Title2'),
P('Trace the data flow from Author to Book to Library, then check what each test expects.', 'Sub2'),
H('1. Decide what each object stores'),
C("Author: name, birth_year\nBook: title, isbn, author (Author object), available_copies\nLibrary: books (dict: ISBN -> Book object)"),
B('The relationships are has-a: a Book stores an Author object; a Library stores Book objects.'),
H('2. Create objects and connect them'),
C("author = Author('John Doe', 1980)\nbook = Book('Intro to Python', '978-...', author, 10)\nlibrary = Library()\nlibrary.add_book(book)"),
B('book.author refers to the same Author object. The library dictionary key is the ISBN; its value is the whole Book.'),
H('3. Add a new book or merge a duplicate'),
C("def add_book(self, book):\n    if book.isbn in self.books:\n        self.books[book.isbn].available_copies += book.available_copies\n    else:\n        self.books[book.isbn] = book"),
B('For a repeated ISBN, update the existing Book object; replacing it would lose the earlier copy count.'),
H('4. Follow references to search and total'),
C("total = sum(b.available_copies for b in self.books.values())\nby_author = [b.title for b in self.books.values()\n             if b.author.name == author_name]\nmatch = [b for b in self.books.values()\n         if b.title == title]"),
B('Search path: Library → Book → Author → name. Title is directly on Book.'),
H('5. Trace one test'),
C("book starts with 10 copies\nborrow_copy(): 10 -> 9\nreturn_copy(): 9 -> 10\nadd duplicate ISBN with 2 copies: 10 -> 12"),
B('A method that “returns” a message must return a string, not print it. Update the count first, then return the exact expected text.'),
H('Exact strings matter'),
C("def __str__(self):\n    return f'Name: {self.name}, Role: {self.role}'\n\n# print(obj) calls __str__ automatically\n# '\\n' inserts a newline in a string"),
B('When an assert fails, inspect the first failing assert. For strings, compare line breaks, spaces, punctuation and the final newline.'),
P('Exam workflow: identify types → write __init__ → implement one method at a time → trace a test → compare the returned value.', 'Small2')]

doc = SheetDoc(str(OUT))
doc.build(story)
print(OUT)
