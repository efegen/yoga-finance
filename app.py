from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func, extract
import csv
import io
import os
from werkzeug.utils import secure_filename
import json
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yoga_finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'yoga-finance-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Yükleme klasörünü oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Modeller
class Student(db.Model):
    """Öğrenciler tablosu"""
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    registration_date = db.Column(db.Date, default=datetime.today)
    notes = db.Column(db.Text)
    lesson_fee = db.Column(db.Float, default=0)
    attendances = db.relationship('StudentAttendance', backref='student', lazy=True, cascade='all, delete-orphan')
    
class StudentAttendance(db.Model):
    """Öğrenci katılım kayıtları"""
    __tablename__ = 'student_attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.today)
    amount = db.Column(db.Float, default=0)
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid
    notes = db.Column(db.Text)

class Product(db.Model):
    """Ürünler tablosu"""
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    price = db.Column(db.Float, default=0)
    stock = db.Column(db.Integer, default=0)
    image_path = db.Column(db.String(200))
    description = db.Column(db.Text)
    sales = db.relationship('ProductSale', backref='product', lazy=True)

class ProductSale(db.Model):
    """Ürün satışları"""
    __tablename__ = 'product_sales'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    sale_date = db.Column(db.Date, nullable=False, default=datetime.today)
    customer_name = db.Column(db.String(100))

class Event(db.Model):
    """Etkinlikler tablosu"""
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date)
    participant_count = db.Column(db.Integer, default=0)
    revenue = db.Column(db.Float, default=0)
    expenses = db.Column(db.Float, default=0)
    description = db.Column(db.Text)

class Category(db.Model):
    """Gelir/Gider kategorileri"""
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'income' veya 'expense'
    
class Transaction(db.Model):
    """İşlemler tablosu"""
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.today)
    type = db.Column(db.String(10), nullable=False)  # 'income' veya 'expense'
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    category = db.relationship('Category', backref='transactions')
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    student = db.relationship('Student', backref='transactions')

class Volunteer(db.Model):
    """Gönüllüler tablosu (personel gibi, maaşsız)"""
    __tablename__ = 'volunteers'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    student = db.relationship('Student', backref='volunteer', uselist=False)
    notes = db.Column(db.Text)
    event_fee = db.Column(db.Float, default=0)  # Etkinlikte verilecek ücret (isteğe bağlı)

class VolunteerSettings(db.Model):
    __tablename__ = 'volunteer_settings'
    id = db.Column(db.Integer, primary_key=True)
    standard_lesson_fee = db.Column(db.Float, default=0)

# Veritabanı başlatma
def init_db():
    """Veritabanını ve örnek verileri oluştur"""
    with app.app_context():
        db.create_all()
        
        # Varsayılan kategoriler
        if Category.query.count() == 0:
            categories = [
                Category(name='Özel Ders', type='income'),
                Category(name='Etkinlik', type='income'),
                Category(name='Ürün Satışı', type='income'),
                Category(name='Diğer Gelir', type='income'),
                Category(name='Kira', type='expense'),
                Category(name='Malzeme', type='expense'),
                Category(name='Yol/Ulaşım', type='expense'),
                Category(name='Vergiler', type='expense'),
                Category(name='Etkinlik Gideri', type='expense'),
                Category(name='Diğer Gider', type='expense')
            ]
            db.session.add_all(categories)
            db.session.commit()

# Kullanıcı giriş kontrolü
def is_logged_in():
    return session.get('logged_in')

@app.before_request
def require_login():
    allowed = ['/login', '/static/', '/favicon.ico']
    if not is_logged_in() and not any(request.path.startswith(a) for a in allowed):
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'efe' and password == '1234':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Ana sayfa (Dashboard)
@app.route('/')
def dashboard():
    """Dashboard sayfasını göster"""
    total_income = db.session.query(func.sum(Transaction.amount)).filter(Transaction.type == 'income').scalar() or 0
    total_expense = db.session.query(func.sum(Transaction.amount)).filter(Transaction.type == 'expense').scalar() or 0
    net_profit = total_income - total_expense
    # Yaklaşan etkinlik
    from datetime import date
    upcoming_event = Event.query.filter(Event.date >= date.today()).order_by(Event.date.asc()).first()
    students = Student.query.order_by(Student.name).all()
    print('DEBUG - Toplam gelir:', total_income, 'Toplam gider:', total_expense)  # Debug satırı
    return render_template('dashboard.html',
                           total_income=total_income,
                           total_expense=total_expense,
                           net_profit=net_profit,
                           upcoming_event=upcoming_event,
                           students=students)

# Öğrenciler
@app.route('/students')
def students():
    """Öğrenciler sayfasını göster"""
    students = Student.query.order_by(Student.name).all()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    """Yeni öğrenci ekle"""
    if request.method == 'POST':
        try:
            student = Student(
                name=request.form['name'],
                phone=request.form.get('phone', ''),
                registration_date=datetime.strptime(request.form['registration_date'], '%Y-%m-%d').date(),
                notes=request.form.get('notes', ''),
                lesson_fee=float(request.form.get('lesson_fee', 0))
            )
            db.session.add(student)
            db.session.commit()
            flash('Öğrenci başarıyla eklendi!', 'success')
            return redirect(url_for('students'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('student_form.html')

@app.route('/students/<int:id>/edit', methods=['GET', 'POST'])
def edit_student(id):
    """Öğrenci düzenle"""
    student = Student.query.get_or_404(id)
    if request.method == 'POST':
        try:
            student.name = request.form['name']
            student.phone = request.form.get('phone', '')
            student.registration_date = datetime.strptime(request.form['registration_date'], '%Y-%m-%d').date()
            student.notes = request.form.get('notes', '')
            student.lesson_fee = float(request.form.get('lesson_fee', 0))
            db.session.commit()
            flash('Öğrenci bilgileri güncellendi!', 'success')
            return redirect(url_for('students'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('student_form.html', student=student)

@app.route('/students/<int:id>')
def student_detail(id):
    """Öğrenci detayları"""
    student = Student.query.get_or_404(id)
    attendances = StudentAttendance.query.filter_by(student_id=id).order_by(StudentAttendance.date.desc()).all()
    transactions = Transaction.query.filter_by(student_id=id).order_by(Transaction.date.desc()).all()
    total_amount = sum(a.amount for a in attendances)
    paid_amount = sum(a.amount for a in attendances if a.payment_status == 'paid')
    pending_amount = total_amount - paid_amount
    return render_template('student_detail.html', 
                         student=student, 
                         attendances=attendances,
                         transactions=transactions,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         pending_amount=pending_amount)

@app.route('/students/<int:id>/attendance/add', methods=['POST'])
def add_attendance(id):
    """Öğrenci katılım kaydı ekle"""
    try:
        student = Student.query.get(id)
        # Eğer öğrenci gönüllüyse, amount'ı ayarlardan al
        volunteer = getattr(student, 'volunteer', None)
        if volunteer:
            settings = VolunteerSettings.query.first()
            amount = settings.standard_lesson_fee if settings else 0
        else:
            amount = float(request.form['amount'])
        attendance = StudentAttendance(
            student_id=id,
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            amount=amount,
            payment_status=request.form['payment_status'],
            notes=request.form.get('notes', '')
        )
        db.session.add(attendance)
        # Eğer ödeme yapıldıysa gelir olarak kaydet
        if attendance.payment_status == 'paid' and attendance.amount > 0:
            category = Category.query.filter_by(name='Özel Ders', type='income').first()
            transaction = Transaction(
                date=attendance.date,
                type='income',
                category_id=category.id,
                amount=attendance.amount,
                description=f'{student.name} - Özel Ders',
                student_id=id
            )
            db.session.add(transaction)
        db.session.commit()
        flash('Katılım kaydı eklendi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('student_detail', id=id))

@app.route('/attendance/<int:id>/mark_paid', methods=['POST'])
def mark_attendance_paid(id):
    """Katılım ödemesini tamamlanmış olarak işaretle"""
    try:
        attendance = StudentAttendance.query.get_or_404(id)
        if attendance.payment_status == 'pending':
            attendance.payment_status = 'paid'
            # Gelir olarak kaydet
            student = Student.query.get(attendance.student_id)
            category = Category.query.filter_by(name='Özel Ders', type='income').first()
            transaction = Transaction(
                date=datetime.today(),
                type='income',
                category_id=category.id,
                amount=attendance.amount,
                description=f'{student.name} - Özel Ders (Tahsilat)',
                student_id=attendance.student_id
            )
            db.session.add(transaction)
            db.session.commit()
            flash('Ödeme kaydedildi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('student_detail', id=attendance.student_id))

# Ürünler
@app.route('/products')
def products():
    """Ürünler sayfasını göster"""
    products = Product.query.all()
    return render_template('products.html', products=products)

@app.route('/products/add', methods=['GET', 'POST'])
def add_product():
    """Yeni ürün ekle"""
    if request.method == 'POST':
        try:
            # Resim yükleme
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    image_path = f"uploads/{filename}"
            
            product = Product(
                name=request.form['name'],
                category=request.form.get('category', ''),
                price=float(request.form['price']),
                stock=int(request.form['stock']),
                image_path=image_path,
                description=request.form.get('description', '')
            )
            db.session.add(product)
            db.session.commit()
            
            flash('Ürün başarıyla eklendi!', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('product_form.html')

@app.route('/products/<int:id>/edit', methods=['GET', 'POST'])
def edit_product(id):
    """Ürün düzenle"""
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            product.name = request.form['name']
            product.category = request.form.get('category', '')
            product.price = float(request.form['price'])
            product.stock = int(request.form['stock'])
            product.description = request.form.get('description', '')
            
            # Yeni resim yüklendiyse
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    # Eski resmi sil
                    if product.image_path:
                        old_path = os.path.join('static', product.image_path)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    # Yeni resmi kaydet
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    product.image_path = f"uploads/{filename}"
            
            db.session.commit()
            flash('Ürün güncellendi!', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('product_form.html', product=product)

@app.route('/products/<int:id>/sell', methods=['POST'])
def sell_product(id):
    """Ürün satışı yap"""
    try:
        product = Product.query.get_or_404(id)
        quantity = int(request.form['quantity'])
        unit_price = float(request.form.get('unit_price', product.price))
        customer_name = request.form.get('customer_name', '')
        
        if quantity > product.stock:
            flash('Stokta yeterli ürün yok!', 'warning')
            return redirect(url_for('products'))
        
        # Satış kaydı
        sale = ProductSale(
            product_id=id,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=quantity * unit_price,
            sale_date=datetime.today(),
            customer_name=customer_name
        )
        db.session.add(sale)
        
        # Stok güncelle
        product.stock -= quantity
        
        # Gelir kaydı
        category = Category.query.filter_by(name='Ürün Satışı', type='income').first()
        transaction = Transaction(
            date=datetime.today(),
            type='income',
            category_id=category.id,
            amount=sale.total_amount,
            description=f'{product.name} - {quantity} adet'
        )
        db.session.add(transaction)
        
        db.session.commit()
        flash('Satış başarıyla kaydedildi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('products'))

@app.route('/products/<int:id>/delete', methods=['POST'])
def delete_product(id):
    """Ürün sil"""
    try:
        product = Product.query.get_or_404(id)
        
        # Resmi sil
        if product.image_path:
            file_path = os.path.join('static', product.image_path)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(product)
        db.session.commit()
        flash('Ürün silindi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('products'))

# Etkinlikler
@app.route('/events')
def events():
    """Etkinlikler sayfasını göster"""
    from datetime import date
    events = Event.query.order_by(Event.date.desc()).all()
    students = Student.query.order_by(Student.name).all()
    today = date.today()
    def event_to_dict(event):
        return {
            'id': event.id,
            'name': event.name,
            'date': event.date.strftime('%Y-%m-%d') if event.date else '',
            'participant_count': event.participant_count,
            'revenue': int(event.revenue) if event.revenue else 0,
            'expenses': int(event.expenses) if event.expenses else 0,
            'description': event.description or ''
        }
    events_dict = [event_to_dict(e) for e in events if e.date and e.date < today]
    return render_template('events.html', events=events_dict, students=students)

@app.route('/events/add', methods=['GET', 'POST'])
def add_event():
    """Yeni etkinlik ekle"""
    students = Student.query.order_by(Student.name).all()
    volunteers = Volunteer.query.all()
    if request.method == 'POST':
        try:
            event = Event(
                name=request.form['name'],
                date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                participant_count=int(request.form.get('participant_count', 0)),
                revenue=float(request.form.get('revenue', 0)),
                expenses=float(request.form.get('expenses', 0)),
                description=request.form.get('description', '')
            )
            db.session.add(event)
            # Gönüllü ataması (şimdilik not olarak sakla)
            volunteer_ids = request.form.getlist('volunteer_ids')
            if volunteer_ids:
                volunteer_names = ', '.join([Volunteer.query.get(int(vid)).student.name for vid in volunteer_ids])
                event.description = (event.description or '') + f"\nGönüllüler: {volunteer_names}"
            # Gelir kaydı (gönüllüler hariç)
            if event.revenue > 0:
                category = Category.query.filter_by(name='Etkinlik', type='income').first()
                transaction = Transaction(
                    date=event.date,
                    type='income',
                    category_id=category.id,
                    amount=event.revenue,
                    description=f'{event.name} - Etkinlik Geliri'
                )
                db.session.add(transaction)
            # Gider kaydı
            if event.expenses > 0:
                category = Category.query.filter_by(name='Etkinlik Gideri', type='expense').first()
                transaction = Transaction(
                    date=event.date,
                    type='expense',
                    category_id=category.id,
                    amount=event.expenses,
                    description=f'{event.name} - Etkinlik Gideri'
                )
                db.session.add(transaction)
            db.session.commit()
            flash('Etkinlik başarıyla eklendi!', 'success')
            return redirect(url_for('events'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('event_form.html', students=students, volunteers=volunteers)

# İşlemler
@app.route('/transactions')
def transactions():
    """İşlemler sayfasını göster"""
    income_categories = Category.query.filter_by(type='income').all()
    expense_categories = Category.query.filter_by(type='expense').all()
    income_categories_dict = [{'id': c.id, 'name': c.name} for c in income_categories]
    expense_categories_dict = [{'id': c.id, 'name': c.name} for c in expense_categories]
    all_transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    return render_template(
        'transactions.html',
        income_categories=income_categories_dict,
        expense_categories=expense_categories_dict,
        transactions=all_transactions
    )

@app.route('/transactions/add', methods=['POST'])
def add_transaction():
    """Yeni işlem ekle"""
    try:
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        trans_type = request.form['type']
        category_id = int(request.form['category_id'])
        amount = float(request.form['amount'])
        description = request.form.get('description', '')
        
        transaction = Transaction(
            date=date,
            type=trans_type,
            category_id=category_id,
            amount=amount,
            description=description
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        flash('İşlem başarıyla eklendi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('transactions'))

@app.route('/transactions/<int:id>/delete', methods=['POST'])
def delete_transaction(id):
    try:
        transaction = Transaction.query.get_or_404(id)
        db.session.delete(transaction)
        db.session.commit()
        flash('İşlem silindi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('transactions'))

# Kategoriler
@app.route('/categories')
def categories():
    """Kategoriler sayfasını göster"""
    income_categories = Category.query.filter_by(type='income').all()
    expense_categories = Category.query.filter_by(type='expense').all()
    return render_template('categories.html', 
                         income_categories=income_categories,
                         expense_categories=expense_categories)

@app.route('/categories/add', methods=['POST'])
def add_category():
    """Yeni kategori ekle"""
    try:
        name = request.form['name']
        cat_type = request.form['type']
        
        category = Category(name=name, type=cat_type)
        db.session.add(category)
        db.session.commit()
        
        flash('Kategori eklendi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('categories'))

@app.route('/categories/<int:id>/delete')
def delete_category(id):
    """Kategori sil"""
    try:
        category = Category.query.get_or_404(id)
        # İlişkili işlemler var mı kontrol et
        if category.transactions:
            flash(f'Bu kategoride {len(category.transactions)} işlem var, silinemez!', 'warning')
        else:
            db.session.delete(category)
            db.session.commit()
            flash('Kategori silindi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
    
    return redirect(url_for('categories'))

# API Endpoints
@app.route('/api/summary')
def api_summary():
    from datetime import date, timedelta

    def get_range_sum(start, end):
        income = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'income',
            Transaction.date >= start,
            Transaction.date <= end
        ).scalar() or 0
        expense = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'expense',
            Transaction.date >= start,
            Transaction.date <= end
        ).scalar() or 0
        return {
            'income': income,
            'expense': expense,
            'net_profit': income - expense
        }

    today = date.today()
    # Bugün
    today_summary = get_range_sum(today, today)
    # Bu hafta (Pazartesi - Bugün)
    week_start = today - timedelta(days=today.weekday())
    week_summary = get_range_sum(week_start, today)
    # Bu ay (Ayın 1'i - Bugün)
    month_start = today.replace(day=1)
    month_summary = get_range_sum(month_start, today)
    # Bu ay ürün satışından elde edilen gelir
    product_income = db.session.query(func.sum(Transaction.amount)).join(Category).filter(
        Transaction.type == 'income',
        Category.name == 'Ürün Satışı',
        Transaction.date >= month_start,
        Transaction.date <= today
    ).scalar() or 0
    # Bu ay özel ders gelirleri
    lesson_income = db.session.query(func.sum(Transaction.amount)).join(Category).filter(
        Transaction.type == 'income',
        Category.name == 'Özel Ders',
        Transaction.date >= month_start,
        Transaction.date <= today
    ).scalar() or 0
    # Bu ay ödenmeyen ders ücretleri
    unpaid_lesson_amount = db.session.query(func.sum(StudentAttendance.amount)).filter(
        StudentAttendance.payment_status == 'pending',
        StudentAttendance.date >= month_start,
        StudentAttendance.date <= today
    ).scalar() or 0
    # Bu ay satılan toplam ürün adedi
    product_sales_count = db.session.query(func.sum(ProductSale.quantity)).filter(
        ProductSale.sale_date >= month_start,
        ProductSale.sale_date <= today
    ).scalar() or 0

    # Bu ay verilen toplam ders sayısı (katılım kaydı)
    monthly_lessons = db.session.query(StudentAttendance).filter(
        StudentAttendance.date >= month_start,
        StudentAttendance.date <= today
    ).count()
    # Sistemdeki toplam öğrenci sayısı
    total_students = Student.query.count()

    # Filtreli özet (isteğe bağlı)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    filtered = {'income': 0, 'expense': 0, 'net_profit': 0}
    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        filtered = get_range_sum(start, end)

    return jsonify({
        'today': today_summary,
        'week': week_summary,
        'month': month_summary,
        'stats': {
            'monthly_lessons': monthly_lessons,
            'total_students': total_students,
            'product_income': product_income,
            'lesson_income': lesson_income,
            'unpaid_lesson_amount': unpaid_lesson_amount,
            'product_sales_count': product_sales_count
        },
        'filtered': filtered
    })

@app.route('/export/csv')
def export_csv():
    """Verileri CSV olarak dışa aktar"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = Transaction.query.order_by(Transaction.date.desc())
    
    if start_date:
        query = query.filter(Transaction.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Transaction.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    
    transactions = query.all()
    
    # CSV oluştur
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Başlıklar
    writer.writerow(['Tarih', 'Tür', 'Kategori', 'Tutar', 'Açıklama'])
    
    # Veriler
    for trans in transactions:
        writer.writerow([
            trans.date.strftime('%Y-%m-%d'),
            'Gelir' if trans.type == 'income' else 'Gider',
            trans.category.name if trans.category else '',
            f'{trans.amount:.2f}',
            trans.description or ''
        ])
    
    # Dosya olarak gönder
    output.seek(0)
    filename = f'yoga_finance_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

# Raporlar
@app.route('/reports')
def reports():
    """Raporlar sayfasını göster"""
    return render_template('reports.html')

@app.route('/api/monthly_report')
def api_monthly_report():
    """Aylık rapor verisi"""
    year = request.args.get('year', datetime.now().year)
    
    months = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
              'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
    
    report_data = []
    total_income = 0
    total_expense = 0
    
    for i, month_name in enumerate(months):
        month = i + 1
        
        # Gelir
        income = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'income',
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar() or 0
        
        # Gider
        expense = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'expense',
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar() or 0
        
        net_profit = income - expense
        
        report_data.append({
            'month': month_name,
            'income': income,
            'expense': expense,
            'net_profit': net_profit
        })
        
        total_income += income
        total_expense += expense
    
    return jsonify({
        'data': report_data,
        'totals': {
            'income': total_income,
            'expense': total_expense,
            'net_profit': total_income - total_expense
        }
    })

@app.route('/api/student_report')
def api_student_report():
    """Öğrenci ödeme raporu"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = db.session.query(
        Student.name,
        func.count(StudentAttendance.id).label('session_count'),
        func.sum(StudentAttendance.amount).label('total_amount'),
        func.sum(func.case([(StudentAttendance.payment_status == 'paid', StudentAttendance.amount)], else_=0)).label('paid_amount')
    ).join(
        StudentAttendance
    )
    
    if start_date:
        query = query.filter(StudentAttendance.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(StudentAttendance.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    
    results = query.group_by(Student.id).all()
    
    report_data = []
    for name, sessions, total, paid in results:
        pending = total - paid if total and paid else (total or 0)
        report_data.append({
            'name': name,
            'sessions': sessions,
            'total': total or 0,
            'paid': paid or 0,
            'pending': pending
        })
    
    return jsonify(report_data)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    settings = {
        'default_vat_rate': 0.18
    }
    return render_template('settings.html', settings=settings)

@app.route('/api/daily_chart')
def api_daily_chart():
    from datetime import date, timedelta
    days = 30
    today = date.today()
    labels = []
    income = []
    expense = []
    for i in range(days-1, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime('%Y-%m-%d'))
        inc = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'income',
            Transaction.date == day
        ).scalar() or 0
        exp = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'expense',
            Transaction.date == day
        ).scalar() or 0
        income.append(inc)
        expense.append(exp)
    return jsonify({'labels': labels, 'income': income, 'expense': expense})

@app.route('/api/monthly_chart')
def api_monthly_chart():
    from datetime import date
    today = date.today()
    labels = []
    income = []
    expense = []
    for i in range(11, -1, -1):
        year = today.year if today.month - i > 0 else today.year - 1
        month = (today.month - i - 1) % 12 + 1
        label = f'{year}-{month:02d}'
        labels.append(label)
        inc = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'income',
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar() or 0
        exp = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.type == 'expense',
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar() or 0
        income.append(inc)
        expense.append(exp)
    return jsonify({'labels': labels, 'income': income, 'expense': expense})

@app.route('/api/category_chart')
def api_category_chart():
    from datetime import datetime
    type_ = request.args.get('type', 'income')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = db.session.query(
        Category.name,
        func.sum(Transaction.amount)
    ).join(Transaction).filter(Category.type == type_)
    if start_date:
        query = query.filter(Transaction.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Transaction.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    query = query.group_by(Category.name)
    results = query.all()
    labels = [r[0] for r in results]
    values = [r[1] or 0 for r in results]
    return jsonify({'labels': labels, 'values': values})

@app.context_processor
def inject_now():
    return {'now': datetime.now}

@app.route('/add_special_lesson', methods=['POST'])
def add_special_lesson():
    student_ids = request.form.getlist('student_ids')
    date = request.form.get('date')
    if not student_ids or not date:
        flash('En az bir öğrenci ve tarih seçmelisiniz.', 'danger')
        return redirect(url_for('dashboard'))
    for sid in student_ids:
        student = Student.query.get(int(sid))
        if not student:
            continue
        # Katılım kaydı
        attendance = StudentAttendance(
            student_id=student.id,
            date=datetime.strptime(date, '%Y-%m-%d').date(),
            amount=student.lesson_fee,
            payment_status='paid',
            notes='Hızlı özel ders kaydı'
        )
        db.session.add(attendance)
        # Gelir kaydı
        category = Category.query.filter_by(name='Özel Ders', type='income').first()
        transaction = Transaction(
            date=attendance.date,
            type='income',
            category_id=category.id if category else None,
            amount=student.lesson_fee,
            description=f'{student.name} - Hızlı özel ders',
            student_id=student.id
        )
        db.session.add(transaction)
    db.session.commit()
    flash('Özel ders katılımları ve gelirler eklendi!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/api/monthly_attendance')
def api_monthly_attendance():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = db.session.query(StudentAttendance, Student).join(Student, StudentAttendance.student_id == Student.id)
    if start_date:
        query = query.filter(StudentAttendance.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(StudentAttendance.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    results = query.order_by(StudentAttendance.date.desc()).all()
    data = []
    for att, student in results:
        data.append({
            'student_name': student.name,
            'date': att.date.strftime('%Y-%m-%d'),
            'notes': att.notes or ''
        })
    return jsonify(data)

@app.route('/api/products')
def api_products():
    products = Product.query.all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock': p.stock
        } for p in products
    ])

@app.route('/volunteers')
def volunteers():
    volunteers = Volunteer.query.order_by(Volunteer.id).all()
    transactions = Transaction.query.all()
    return render_template('volunteers.html', volunteers=volunteers, transactions=transactions)

@app.route('/volunteers/add', methods=['GET', 'POST'])
def add_volunteer():
    # Sadece gönüllü olmayan öğrenciler
    students = Student.query.outerjoin(Volunteer, Student.id == Volunteer.student_id).filter(Volunteer.id == None).order_by(Student.name).all()
    if request.method == 'POST':
        selected_ids = request.form.getlist('student_ids')
        if not selected_ids:
            flash('En az bir öğrenci seçmelisiniz.', 'warning')
            return render_template('volunteer_bulk_add.html', students=students)
        for sid in selected_ids:
            volunteer = Volunteer(
                student_id=int(sid)
            )
            db.session.add(volunteer)
        db.session.commit()
        flash('Seçilen öğrenciler gönüllü olarak eklendi!', 'success')
        return redirect(url_for('volunteers'))
    return render_template('volunteer_bulk_add.html', students=students)

@app.route('/volunteers/<int:id>/edit', methods=['GET', 'POST'])
def edit_volunteer(id):
    """Gönüllü düzenle"""
    volunteer = Volunteer.query.get_or_404(id)
    # Sadece gönüllü olmayan öğrenciler + mevcut gönüllünün öğrencisi
    students = Student.query.outerjoin(Volunteer, Student.id == Volunteer.student_id).filter((Volunteer.id == None) | (Student.id == volunteer.student_id)).order_by(Student.name).all()
    if request.method == 'POST':
        try:
            volunteer.student_id = int(request.form['student_id'])
            volunteer.notes = request.form.get('notes', '')
            volunteer.event_fee = float(request.form.get('event_fee', 0))
            db.session.commit()
            flash('Gönüllü güncellendi!', 'success')
            return redirect(url_for('volunteers'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('volunteer_form.html', volunteer=volunteer, students=students)

@app.route('/volunteers/<int:id>/delete', methods=['POST'])
def delete_volunteer(id):
    try:
        volunteer = Volunteer.query.get_or_404(id)
        db.session.delete(volunteer)
        db.session.commit()
        flash('Gönüllü silindi!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('volunteers'))

@app.route('/volunteer_settings', methods=['GET', 'POST'])
def volunteer_settings():
    settings = VolunteerSettings.query.first()
    if not settings:
        settings = VolunteerSettings(standard_lesson_fee=0)
        db.session.add(settings)
        db.session.commit()
    if request.method == 'POST':
        try:
            settings.standard_lesson_fee = float(request.form.get('standard_lesson_fee', 0))
            db.session.commit()
            flash('Ayarlar güncellendi!', 'success')
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('volunteer_settings.html', settings=settings)

@app.route('/volunteers/<int:id>/pay_salary', methods=['GET', 'POST'])
def pay_salary(id):
    from datetime import date
    volunteer = Volunteer.query.get_or_404(id)
    # Geçmiş etkinlikler (bugünden eski)
    events = Event.query.filter(Event.date < date.today()).order_by(Event.date.desc()).all()
    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            note = request.form.get('note', '')
            event_id = request.form.get('event_id')
            event = Event.query.get(int(event_id)) if event_id else None
            # Gider kategorisi: Maaş Ödemesi
            category = Category.query.filter_by(name='Maaş Ödemesi', type='expense').first()
            if not category:
                category = Category(name='Maaş Ödemesi', type='expense')
                db.session.add(category)
                db.session.commit()
            desc = f"{volunteer.student.name} - Gönüllü maaş ödemesi. "
            if event:
                desc += f"Etkinlik: {event.name} ({event.date.strftime('%Y-%m-%d')})"
            if note:
                desc += f" Not: {note}"
            transaction = Transaction(
                date=datetime.today(),
                type='expense',
                category_id=category.id if category else None,
                amount=amount,
                description=desc,
                student_id=volunteer.student_id
            )
            db.session.add(transaction)
            db.session.commit()
            flash('Maaş ödemesi kaydedildi!', 'success')
            return redirect(url_for('volunteers'))
        except Exception as e:
            flash(f'Hata: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('pay_salary.html', volunteer=volunteer, events=events)

@app.route('/debug_transactions')
def debug_transactions():
    out = []
    for t in Transaction.query.order_by(Transaction.id.desc()).all():
        out.append(f'id={t.id}, amount={t.amount}, desc={t.description}, student_id={t.student_id}')
    return '<br>'.join(out)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)