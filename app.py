from flask import Flask, render_template, session, redirect, request, jsonify
from functools import wraps
import pymongo
import uuid
from werkzeug.utils import secure_filename
import os
from passlib.hash import pbkdf2_sha256

app = Flask(__name__)
app.secret_key = uuid.uuid4().hex

# Database
client = pymongo.MongoClient('localhost', 27017)
db = client.auth_app

# Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'images')  # Correct way
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DEFAULT_PROFILE_PICTURE = '/static/images/default_profile.jpg'  # Default profile picture path
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User:
    def start_session(self, user):
        del user['password']
        session['logged_in'] = True
        session['user'] = user
        return jsonify(user), 200

    def signup(self):
        # Create the user object
        user = {
            "_id": uuid.uuid4().hex,
            "name": request.form.get('name'),
            "email": request.form.get('email'),
            "password": request.form.get('password'),
            "profile_picture": DEFAULT_PROFILE_PICTURE  # Set default profile picture
        }

        # Encrypt the password
        user['password'] = pbkdf2_sha256.encrypt(user['password'])

        # Check for existing email address
        if db.users.find_one({"email": user['email']}):
            return jsonify({"error": "Email address already in use"}), 400
        
        if db.users.insert_one(user):
            return self.start_session(user)
       
        return jsonify({"error": "Signup failed"}), 400
    
    def signout(self):
        session.clear()
        return redirect('/')
    
    def login(self):
        user = db.users.find_one({
            "email": request.form.get('email')
        })

        if user and pbkdf2_sha256.verify(request.form.get('password'), user['password']):
            return self.start_session(user)
        
        return jsonify({"error": "Invalid login credentials"}), 401
    
    def update_profile(self, user_id, filename=None, name=None, password=None):
        update_fields = {}

        if filename:
            update_fields['profile_picture'] = '/static/images/' + filename
        if name:
            update_fields['name'] = name
        if password:
            update_fields['password'] = pbkdf2_sha256.encrypt(password)

        db.users.update_one(
            {"_id": user_id},
            {"$set": update_fields}
        )
        user = db.users.find_one({"_id": user_id})
        session['user'] = user
        del user['password']
        return user

# Decorators
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            return redirect('/')
    return wrap

# Routes
@app.route('/user/signup', methods=['POST'])
def signup():
    return User().signup()

@app.route('/user/signout')
def signout():
    return User().signout()

@app.route('/user/login', methods=['POST'])
def login():
    return User().login()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/profile/')
@login_required
def profile():
    user = session['user']
    return render_template('profile.html', user=user)  # Pass the user object to the template

@app.route('/update_info', methods=['POST'])
@login_required
def update_info():
    if request.method == 'POST':
        user_id = session['user']['_id']
        name = request.form.get('name')
        old_password = request.form.get('old_password')  # New field for old password
        new_password = request.form.get('password')  # New password field
        confirm_password = request.form.get('confirm_password')  # Confirm new password field
        file = request.files.get('file')  # Use .get() to avoid KeyError if no file is uploaded
        filename = None

        # Query the current user from the database
        user = db.users.find_one({"_id": user_id})

        # Check if the old password is correct
        if old_password!='':
            if not pbkdf2_sha256.verify(old_password, user['password']):
                return jsonify({"error": "Old password is incorrect"}), 400
            # Check if new password and confirm password match
            if new_password and new_password != confirm_password:
                return jsonify({"error": "New passwords do not match"}), 400

        if file:
            if allowed_file(file.filename):
                try:
                    # Create a unique filename
                    file_extension = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(user_id + '.' + file_extension)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                except Exception as e:
                    return jsonify({"error": "File upload failed: " + str(e)}), 500
            else:
                return "Invalid file format. Please upload an image."

        # Update the user's profile information, including new password if provided
        user = User().update_profile(user_id, filename, name, new_password)
        return render_template('profile.html', user=user)

if __name__ == '__main__':
    # Ensure the upload folder exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)