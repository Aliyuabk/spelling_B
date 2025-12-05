from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import os, csv
from io import TextIOWrapper

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# SQLite configuration
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -----------------------
# Models
# -----------------------
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    school = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False, default=0)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_number = db.Column(db.Integer, nullable=False, default=100)

class EliminatedStudent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    school = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False, default=0)


# -----------------------
# Create tables
# -----------------------
with app.app_context():
    db.create_all()
    if not Setting.query.first():
        db.session.add(Setting(max_number=100))
        db.session.commit()

# -----------------------
# Admin Panel
# -----------------------
@app.route("/", methods=["GET"])
def admin():
    students = Student.query.order_by(Student.points.desc(), Student.name.asc()).all()
    setting = Setting.query.first()
    max_number = setting.max_number if setting else 100
    return render_template("admin.html", students=students, max_number=max_number)

@app.route("/add_student", methods=["POST"])
def add_student():
    name = request.form.get("name", "").strip()
    school = request.form.get("school", "").strip()
    points = request.form.get("points", "0").strip()

    if not name or not school:
        flash("Student name and school are required", "error")
        return redirect(url_for("admin"))
    
    try:
        points = int(points)
    except:
        flash("Points must be an integer", "error")
        return redirect(url_for("admin"))
    
    db.session.add(Student(name=name, school=school, points=points))
    db.session.commit()
    flash("Student added successfully", "success")
    return redirect(url_for("admin"))

@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    if "csv_file" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("admin"))
    
    file = request.files["csv_file"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("admin"))
    
    try:
        csv_file = TextIOWrapper(file, encoding="utf-8")
        reader = csv.reader(csv_file)
        count = 0
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            school = row[1].strip()
            points = int(row[2]) if len(row) > 2 and row[2].isdigit() else 0
            if name and school:
                db.session.add(Student(name=name, school=school, points=points))
                count += 1
        db.session.commit()
        flash(f"{count} students added successfully", "success")
    except Exception as e:
        flash(f"Error processing CSV: {e}", "error")
    return redirect(url_for("admin"))

@app.route("/delete_student/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    s = Student.query.get_or_404(student_id)
    db.session.delete(s)
    db.session.commit()
    flash("Student deleted", "success")
    return redirect(url_for("admin"))

@app.route("/update_max_number", methods=["POST"])
def update_max_number():
    max_number = request.form.get("max_number")
    try:
        max_number = int(max_number)
        if max_number <= 0:
            raise ValueError("Maximum number must be > 0")
        setting = Setting.query.first()
        setting.max_number = max_number
        db.session.commit()
        flash("Maximum number updated successfully", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("admin"))

# -----------------------
# Student Pages
# -----------------------
@app.route("/select_student")
def select_student():
    students = Student.query.order_by(Student.name).all()
    return render_template("select_student.html", students=students)

@app.route("/choose_number/<int:student_id>")
def choose_number_for_student(student_id):
    student = Student.query.get_or_404(student_id)
    setting = Setting.query.first()
    max_number = setting.max_number if setting else 100
    numbers = list(range(1, max_number + 1))

    # Ensure answered_numbers exists and is a dict
    answered = session.get("answered_numbers")
    if not isinstance(answered, dict):
        answered = {}

    number_cards = []
    for n in numbers:
        status = answered.get(str(n))  # 'pending', 'correct', 'incorrect'
        number_cards.append({"number": n, "status": status})

    return render_template("choose_number.html", student=student, number_cards=number_cards)

@app.route("/start_quiz/<int:student_id>/<int:number>")
def start_quiz(student_id, number):
    student = Student.query.get_or_404(student_id)

    if "answered_numbers" not in session or not isinstance(session.get("answered_numbers"), dict):
        session["answered_numbers"] = {}

    session["answered_numbers"][str(number)] = "pending"
    session.modified = True

    return redirect(url_for("spell_word", student_id=student.id, number=number))

@app.route("/spell_word/<int:student_id>/<int:number>", methods=["GET", "POST"])
def spell_word(student_id, number):
    student = Student.query.get_or_404(student_id)

    if "answered_numbers" not in session or not isinstance(session.get("answered_numbers"), dict):
        session["answered_numbers"] = {}

    word_list = ["apple", "banana", "cherry", "date", "elephant"]
    total_words = len(word_list)
    word_index = (number - 1) % total_words
    word = word_list[word_index]
    position = 1

    if request.method == "POST":
        typed_word = request.form.get("typed_word", "").strip()
        result = request.form.get("result")

        if result == "correct":
            student.points += 1
            db.session.commit()
            flash(f"{student.name} answered correctly! +1 point", "success")
            session["answered_numbers"][str(number)] = "correct"
            return redirect(url_for("select_student"))
        else:
            eliminated = EliminatedStudent(
                name=student.name,
                school=student.school,
                points=student.points
            )
            db.session.add(eliminated)
            db.session.delete(student)
            db.session.commit()
            flash(f"{student.name} is eliminated!", "error")
            session["answered_numbers"][str(number)] = "incorrect"
            session.modified = True
            return redirect(url_for("select_student"))

        session.modified = True
        return redirect(url_for("choose_number_for_student", student_id=student.id))

    return render_template(
        "spell_word.html",
        student=student,
        word=word,
        word_number=number,
        total=total_words,
        position=position
    )


# -----------------------
# Overall Results
# -----------------------
@app.route("/overall_results")
def overall_results():
    # Get all students sorted by points descending
    students = Student.query.order_by(Student.points.desc(), Student.name.asc()).all()

    # Prepare table data
    # 'total' can be number of answered numbers from session
    answered_numbers = session.get("answered_numbers", {})

    table_data = []
    for s in students:
        # Count how many numbers the student attempted
        # If session tracks per student, you may need a more complex structure
        total_attempted = sum(1 for key, status in answered_numbers.items() if status in ["correct", "incorrect"])
        table_data.append({
            "name": s.name,
            "school": s.school,
            "points": s.points,
            "total": total_attempted
        })

    return render_template("overall_result.html", table_data=table_data)


# -----------------------
# Run Server
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
