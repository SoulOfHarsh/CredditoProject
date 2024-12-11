from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_bcrypt import Bcrypt
import supabase
from datetime import timedelta, datetime
from authlib.integrations.flask_client import OAuth
import os
import uuid
from werkzeug.utils import secure_filename

def calculate_repayment_date(loan_term):
    today = datetime.now().date()
    
    if loan_term == "1week":
        return today + timedelta(weeks=1)
    elif loan_term == "1month":
        return today + timedelta(weeks=4)
    elif loan_term == "3months":
        return today + timedelta(weeks=12)
    elif loan_term == "6months":
        return today + timedelta(weeks=24)
    elif loan_term == "12months":
        return today + timedelta(weeks=48)
    elif loan_term == "24months":
        return today + timedelta(weeks=96)
    else:
        return today 

app = Flask(__name__)
app.secret_key = "your_secret_key"
bcrypt = Bcrypt(app)


UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'jpg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='478919675453-lbrbdpnq0f7dtkg6bo4jk21pocba2d8v.apps.googleusercontent.com',
    client_secret='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',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    refresh_token_url=None,
    refresh_token_params=None,
    client_kwargs={'scope': 'openid profile email'},
)

SUPABASE_URL = "https://ebdwgxrcpfipbgmjiktx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImViZHdneHJjcGZpcGJnbWppa3R4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzMyMzczNzMsImV4cCI6MjA0ODgxMzM3M30.ROkctnTe9GvarxnrAkSYNBLMBzzL8lByRqE1F3ry4Xg"
supabase_client = supabase.create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/google/login")
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/google/authorize")
def google_authorize():
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token)

    email = user_info['email']
    existing_user = supabase_client.table("users").select("*").eq("email", email).execute()

    if not existing_user.data:
        first_name = user_info.get('given_name')
        last_name = user_info.get('family_name')

        supabase_client.table("users").insert({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": "user",
        }).execute()

    session['logged_in'] = True
    session['user_id'] = user_info.get('sub')
    session['role'] = 'user' 
    flash("Successfully logged in with Google", "success")
    return redirect(url_for("homepage"))

@app.route("/")
def home():
    is_logged_in = session.get('logged_in', False)
    return render_template('homepage.html', is_logged_in=is_logged_in)

@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        first_name = request.form.get("first-name")
        last_name = request.form.get("last-name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm-password")

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for("apply"))

        existing_user = supabase_client.table("users").select("*").eq("email", email).execute()

        if existing_user.data:
            flash("Email already exists. Please choose another.", "error")
            return redirect(url_for("apply"))

        supabase_client.table("users").insert({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password, 
            "role": "user"
        }).execute()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("apply.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        response = supabase_client.table("users").select("*").eq("email", email).execute()

        if not response.data:
            flash("User not found!", "error")
            return redirect(url_for("login"))

        user = response.data[0]

        if user["password"] != password:
            flash("Incorrect password. Please try again.", "error")
            return redirect(url_for("login"))

        # Store session data
        session['logged_in'] = True
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['full_name'] = f"{user['first_name']} {user['last_name']}"

        if user["role"] == "admin":
            flash("Welcome, Admin!", "success")
            return redirect(url_for("overview"))
        elif user["role"] == "user":
            flash("Welcome, User!", "success")
            return redirect(url_for("homepage"))
        else:
            flash("Role not recognized.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route('/homepage')
def homepage():
    is_logged_in = session.get('logged_in', False)
    full_name = session.get('full_name', "Guest")
    return render_template('homepage.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route('/about')
def about():
    is_logged_in = session.get('logged_in', False)
    full_name = session.get('full_name', "Guest")
    return render_template('about.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route('/documents', methods=['GET', 'POST'])
def documents():
    is_logged_in = session.get('logged_in', False)
    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    if not is_logged_in:
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    if request.method == 'POST':
        file = request.files.get('file')

        if not file:
            flash("No file selected.", "error")
            return redirect(url_for('documents'))

        if not (file.filename.lower().endswith('.jpg') or file.filename.lower().endswith('.png')):
            flash("Only JPG and PNG files are allowed.", "error")
            return redirect(url_for('documents'))

        upload_folder = 'static/uploads/'

        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        filename = f"{user_id}_{file.filename}"
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        existing_id = supabase_client.table("id_verification").select("*").eq("user_id", user_id).execute()

        id_data = {
            "user_id": user_id,
            "id_card_image_url": file_path
        }

        if existing_id.data:
            supabase_client.table("id_verification").update(id_data).eq("user_id", user_id).execute()
            flash("ID verification updated successfully.", "success")
        else:
            supabase_client.table("id_verification").insert(id_data).execute()
            supabase_client.table("users").update({"has_id_verified": True}).eq("id", user_id).execute()
            flash("ID verification submitted successfully.", "success")

        return redirect(url_for('information'))

    return render_template('documents.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route("/fill_out", methods=["GET", "POST"])
def fill_out():
    is_logged_in = session.get('logged_in', False)
    if not is_logged_in:
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    if request.method == "POST":
        full_name = request.form.get("fullName").strip()
        dob = request.form.get("dob").strip()
        gender = request.form.get("gender").strip()
        marital_status = request.form.get("maritalStatus").strip()
        phone = request.form.get("phone").strip()
        email = request.form.get("email").strip()
        employment = request.form.get("employment").strip()

        if not all([full_name, dob, gender, marital_status, phone, email, employment]):
            flash("All fields are required.", "error")
            return redirect(url_for("fill_out"))

        personal_info_data = {
            "user_id": user_id,
            "full_name": full_name,
            "date_of_birth": dob,
            "gender": gender,
            "marital_status": marital_status,
            "phone_number": phone,
            "email": email,
            "employment_info": employment
        }

        existing_info = supabase_client.table("personal_info").select("*").eq("user_id", user_id).execute()

        if existing_info.data:
            supabase_client.table("personal_info").update(personal_info_data).eq("user_id", user_id).execute()
            flash("Personal information updated successfully.", "success")
        else:
            supabase_client.table("personal_info").insert(personal_info_data).execute()
            supabase_client.table("users").update({"has_personal_info": True}).eq("id", user_id).execute()
            flash("Personal information saved successfully.", "success")

        return redirect(url_for("information"))

    return render_template('fill_out.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route("/information", methods=["GET", "POST"])
def information():
    is_logged_in = session.get('logged_in', False)
    if not is_logged_in:
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    
    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    user_data = supabase_client.table("users").select("has_personal_info, has_id_verified")\
        .eq("id", user_id).execute().data[0]

    if request.method == "POST":
        loan_data = session.pop('loan_data', None)
        if not loan_data:
            flash("Loan application failed.", "error")
            return redirect(url_for("order"))

        response = supabase_client.table("loans").insert(loan_data).execute()
        if response.data:
            flash("Loan successfully applied!", "success")
            return redirect(url_for("status"))
        else:
            flash("Loan application failed.", "error")

    return render_template('information.html', user_data=user_data, is_logged_in=is_logged_in, full_name=full_name)

@app.route('/loan_history')
def loan_history():
    is_logged_in = session.get('logged_in', False)
    
    if not is_logged_in:
        flash("You must be logged in to view your loan history.", "error")
        return redirect(url_for("login"))
    
    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    loans_response = supabase_client.table("loans").select("*").eq("user_id", user_id).order("borrow_date", desc=True).execute()

    if not loans_response.data:
        flash("No loan history available.", "info")
        return render_template('loan_history.html', is_logged_in=is_logged_in, loans=[], full_name=full_name)

    loans = loans_response.data

    return render_template('loan_history.html', is_logged_in=is_logged_in, loans=loans, full_name=full_name)

@app.route('/order', methods=["GET", "POST"])
def order():
    if not session.get('logged_in'):
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    
    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    active_loans = supabase_client.table("loans").select("*")\
        .eq("user_id", user_id).in_("status", ["pending", "paying"]).execute().data

    if active_loans:
        flash("You cannot apply for a loan while having active or pending loans.", "error")
        return redirect(url_for("loan_history"))

    if request.method == "POST":
        loan_amount_str = request.form.get("loan-amount")
        loan_type = request.form.get("loan-type")
        loan_term = request.form.get("loan-term")

        if not all([loan_amount_str, loan_type, loan_term]):
            flash("Please fill in all fields.", "error")
            return redirect(url_for("order"))

        try:
            loan_amount = float(loan_amount_str)
        except ValueError:
            flash("Invalid loan amount.", "error")
            return redirect(url_for("order"))

        loan_data = {
            "user_id": user_id,
            "loan_amount": loan_amount,
            "loan_type": loan_type,
            "loan_term": loan_term,
            "interest_rate": 20.0,
            "borrow_date": datetime.now().date().isoformat(),
            "repayment_date": calculate_repayment_date(loan_term).isoformat(),
            "status": "pending"
        }
        session['loan_data'] = loan_data
        return redirect(url_for("information"))

    return render_template('order.html', full_name=full_name)

@app.route('/personal_info')
def personal_info():
    is_logged_in = session.get('logged_in', False)
    
    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    if not is_logged_in or not user_id:
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    response = supabase_client.table("personal_info").select("*").eq("user_id", user_id).execute()

    personal_info = response.data[0] if response.data else None

    return render_template(
        'personal_info.html', 
        is_logged_in=is_logged_in, 
        personal_info=personal_info, full_name=full_name
    )
    
@app.route('/privacy_policy')
def privacy_policy():
    is_logged_in = session.get('logged_in', False)
    full_name = session.get('full_name', "Guest")
    return render_template('privacy_policy.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route("/status")
def status():
    is_logged_in = session.get('logged_in', False)
    if not is_logged_in:
        flash("You must be logged in to view your loan status.", "error")
        return redirect(url_for("login"))

    user_id = session.get('user_id')
    loan_response = supabase_client.table("loans").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()

    if not loan_response.data:
        flash("No loan found. Please place an order first.", "error")
        return redirect(url_for("order"))

    loan = loan_response.data[0]
    interest_rate = 20.0
    total_with_interest = loan["loan_amount"] * (1 + (interest_rate / 100))

    return render_template('status.html', is_logged_in=is_logged_in, loan=loan, total_with_interest=total_with_interest)

@app.route('/verification', methods=["GET", "POST"])
def verification():
    is_logged_in = session.get('logged_in', False)
    if not is_logged_in:
        flash("You must be logged in to access this page.", "error")
        return redirect(url_for("login"))

    full_name = session.get('full_name', "Guest")
    user_id = session.get('user_id')

    if request.method == "POST":
        file = request.files.get("id-image")
        if file:
            file.save(os.path.join("uploads", file.filename))  
            file_url = f"/uploads/{file.filename}"  
            id_verification_data = {
                "user_id": user_id,
                "id_card_image_url": file_url,
                "verified": False  
            }
            response = supabase_client.table("id_verification").insert(id_verification_data).execute()

            if response.data:
                flash("Your ID has been uploaded successfully. Awaiting verification.", "success")
                return redirect(url_for("information"))
            else:
                flash("There was an error uploading your ID. Please try again.", "error")

    return render_template('verification.html', is_logged_in=is_logged_in, full_name=full_name)

@app.route('/loan_management')
def loan_management():
    is_logged_in = session.get('logged_in', False)
    
    if not is_logged_in:
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')  
    
    # Fetch only pending loans
    loans_response = supabase_client.table('loans').select('*').eq('status', 'pending').execute()
    loans = loans_response.data

    loan_data = []
    for loan in loans:
        user_info_response = supabase_client.table('personal_info').select('*').eq('user_id', loan['user_id']).execute()
        personal_info = user_info_response.data[0] if user_info_response.data else None

        id_verification_response = supabase_client.table('id_verification').select('id_card_image_url').eq('user_id', loan['user_id']).execute()
        id_card_image_url = id_verification_response.data[0]['id_card_image_url'] if id_verification_response.data else None
        
        loan_data.append({
            'full_name': personal_info['full_name'] if personal_info else 'Unknown',
            'loan_amount': loan['loan_amount'],
            'loan_term': loan['loan_term'],
            'loan_status': loan['status'],
            'loan_id': loan['id'],
            'user_id': loan['user_id'],
            'id_card_image_url': id_card_image_url
        })

    return render_template('loan_management.html', is_logged_in=is_logged_in, loans=loan_data)

@app.route('/update_loan_status/<int:loan_id>/<string:action>', methods=['POST'])
def update_loan_status(loan_id, action):
    if action not in ['approve', 'reject']:
        return {"success": False}, 400

    new_status = 'paying' if action == 'approve' else 'rejected'

    response = supabase_client.table('loans').update({'status': new_status}).eq('id', loan_id).execute()

    if response.status_code == 200:
        return {"success": True}
    else:
        return {"success": False}, 500

@app.route('/get_user_info/<int:user_id>')
def get_user_info(user_id):
    personal_info_response = supabase_client.table('personal_info').select('*').eq('user_id', user_id).execute()
    personal_info = personal_info_response.data[0] if personal_info_response.data else None
    
    if personal_info:
        return {
            'full_name': personal_info['full_name'],
            'date_of_birth': personal_info['date_of_birth'],
            'gender': personal_info['gender'],
            'marital_status': personal_info['marital_status'],
            'phone_number': personal_info['phone_number'],
            'email': personal_info['email'],
            'employment_info': personal_info['employment_info'],
        }
    else:
        return {"error": "User information not found"}, 404

@app.route('/user_management')
def user_management():
    is_logged_in = session.get('logged_in', False)
    
    response = supabase_client.table('users').select(
        'id, first_name, last_name, email, role, personal_info (full_name, phone_number), loans (loan_amount, status, repayment_date)'
    ).eq('role', 'user').execute()  
    
    if 'error' in response.data:
        flash(f"Error fetching users: {response.data['error']}")
        return redirect(url_for('home'))
    
    users = response.data
    
    processed_users = []
    for user in users:
        user_info = user.get('personal_info') 
        loans = user.get('loans') 

        if user_info:
            user_info = user_info[0] if isinstance(user_info, list) else user_info  
            
        active_loans = [loan for loan in loans if loan['status'] in ['active', 'paying']] if loans else []
        
        for loan in active_loans:
            loan['repayment_amount'] = loan['loan_amount'] * 1.20  

        processed_users.append({
            'full_name': user_info.get('full_name', 'N/A') if user_info else 'N/A',
            'email': user.get('email', 'N/A'),
            'phone_number': user_info.get('phone_number', 'N/A') if user_info else 'N/A',
            'active_loans': active_loans,
        })

    return render_template('user_management.html', is_logged_in=is_logged_in, users=processed_users)

@app.route('/overview')
def overview():
    is_logged_in = session.get('logged_in', False)

    if not is_logged_in or session.get('role') != 'admin':
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for('home'))

    loans_response = supabase_client.table('loans').select('*').in_('status', ['paying', 'paid']).execute()
    loans = loans_response.data

    total_loans = len(loans)
    total_loan_amount = sum(loan["loan_amount"] for loan in loans)
    total_repaid_amount = sum(loan["loan_amount"] * (1 + loan["interest_rate"] / 100) for loan in loans_response.data)

    return render_template('overview.html', is_logged_in=is_logged_in,
                           total_loans=total_loans,
                           total_loan_amount=total_loan_amount,
                           total_repaid_amount=total_repaid_amount)
    
@app.route('/manage_loan')
def manage_loan():
    is_logged_in = session.get('logged_in', False)

    if not is_logged_in or session.get('role') != 'admin':
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for('home'))

    loans_response = supabase_client.table('loans').select('*').eq('status', 'paying').execute()
    loans = loans_response.data

    loan_data = []
    for loan in loans:
        user_info_response = supabase_client.table('personal_info').select('*').eq('user_id', loan['user_id']).execute()
        personal_info = user_info_response.data[0] if user_info_response.data else None

        loan_data.append({
            'full_name': personal_info['full_name'] if personal_info else 'Unknown',
            'loan_amount': loan['loan_amount'],
            'loan_term': loan['loan_term'],
            'loan_status': loan['status'],
            'loan_id': loan['id'],
            'repayment': loan['loan_amount'] * 1.2, 
        })

    return render_template('manage_loan.html', is_logged_in=is_logged_in, loans=loan_data)

@app.route('/mark_as_paid/<int:loan_id>', methods=['POST'])
def mark_as_paid(loan_id):
    try:
        response = supabase_client.table('loans').update(
            {'status': 'paid', 'payment_date': datetime.now().strftime('%Y-%m-%d')}
        ).eq('id', loan_id).execute()

        if response.data: 
            return {"success": True}
        else:
            return {"success": False}, 500
    except Exception as e:
        print("Error:", e)
        return {"success": False}, 500

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
