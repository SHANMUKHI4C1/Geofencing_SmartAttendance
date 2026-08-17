from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from flask_mail import Message
import bcrypt
from db import db
from flask import session
import datetime
import pytz
import secrets
import hashlib

# Import mail instance (will be set after app initialization)
mail = None

def init_mail(mail_instance):
    """Initialize mail instance from app.py"""
    global mail
    mail = mail_instance

auth_bp = Blueprint("auth", __name__)   # ✅ FIXED

ADMIN_ID = "admin123"
ADMIN_PASS = "admin@123"

def validate_session():
    """Validate if current session is still active in database"""
    username = session.get("username")
    session_token = session.get("session_token")
    role = session.get("role")
    
    # Skip validation for admin users
    if role == "admin":
        return True
    
    # Check if session data exists
    if not username or not session_token:
        return False
    
    # Fetch user from database
    user = db.users.find_one({"username": username})
    if not user:
        return False
    
    # Check if session token matches
    if user.get("active_session") != session_token:
        return False
    
    return True

def require_valid_session():
    """Decorator to protect routes with session validation"""
    if not validate_session():
        # Clear invalid session
        session.clear()
        return redirect("/?error=session_expired")
    return None

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    error = None
    
    if request.method == "POST":
        user = request.form["username"]
        pwd = request.form["password"]

        # Handle admin login (no session restriction for admin)
        if user == ADMIN_ID and pwd == ADMIN_PASS:
            session["admin_login_time"] = datetime.datetime.now().isoformat()
            session["role"] = "admin"
            session["username"] = user
            return redirect("/admin")

        # Handle student login with session restriction
        u = db.users.find_one({"username": user})
        if u and bcrypt.checkpw(pwd.encode(), u["password"]):
            
            # Check if user already has an active session
            active_session = u.get("active_session")
            force_login = request.form.get("force_login") == "true"
            
            if active_session is not None and not force_login:
                # Show session conflict message with option to force login
                error = "session_conflict"
                return render_template("login.html", error=error, username=user)
            
            # Generate unique session token using secrets.token_hex
            session_token = secrets.token_hex(32)
            
            # Store it in database as active_session (overwrites existing if force_login)
            db.users.update_one(
                {"username": user},
                {"$set": {"active_session": session_token}}
            )
            
            # Save username and token in Flask session
            session["role"] = "student"
            session["username"] = user
            session["session_token"] = session_token
            
            return redirect("/student")
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    success = None
    error = None
    
    if request.method == "POST":
        user = request.form["username"]
        email = request.form["email"]
        pwd = request.form["password"]
        confirm_pwd = request.form.get("confirm_password")
        
        # Validate password match (frontend validation backup)
        if pwd != confirm_pwd:
            error = "Passwords do not match"
            return render_template("register.html", error=error)
        
        # Validate email format (basic server-side validation)
        import re
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_regex, email):
            error = "Please enter a valid email address"
            return render_template("register.html", error=error)
        
        # Check if username already exists
        existing_user = db.users.find_one({"username": user})
        if existing_user:
            error = "Username already exists"
            return render_template("register.html", error=error)
        
        # Check if email already exists
        existing_email = db.users.find_one({"email": email})
        if existing_email:
            error = "Email address already registered"
            return render_template("register.html", error=error)
        
        # Hash password and create user
        hashed_pwd = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())
        
        db.users.insert_one({
            "username": user,
            "email": email,
            "password": hashed_pwd,
            "role": "student",
            "active_session": None,  # Add active session field
            "created_at": datetime.datetime.now()
        })
        
        success = "Account created successfully! You can now login."
        return render_template("register.html", success=success)
    
    return render_template("register.html")

# ✅ ADD THESE BELOW

@auth_bp.route("/student")
def student_dashboard():
    # Validate session for students
    validation_result = require_valid_session()
    if validation_result:
        return validation_result
    
    role = session.get("role", "guest")
    username = session.get("username", "guest")
    return render_template("student.html", role=role, username=username)

@auth_bp.route("/admin")
def admin_dashboard():
    # Check if user has admin role
    if session.get("role") != "admin":
        return "403 Unauthorized - Admin access required", 403
    
    role = session.get("role", "guest")
    username = session.get("username", "admin")
    return render_template("admin.html", role=role, username=username)


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to login"""
    # Get username from session
    username = session.get("username")
    role = session.get("role")
    
    # Update database: active_session = None (for students only)
    if username and role == "student":
        db.users.update_one(
            {"username": username},
            {"$set": {"active_session": None}}
        )
    
    # Clear Flask session
    session.clear()
    
    return redirect("/?message=logged_out")


# ✅ FORGOT PASSWORD FUNCTIONALITY
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    success = None
    error = None
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not email:
            error = "Please enter your email address"
            return render_template("forgot_password.html", error=error)
        
        print(f"🔍 Forgot password request for email: {email}")
        
        # Find user by email with better error handling
        try:
            # Try different query methods for compatibility
            user = None
            
            # Method 1: Direct query
            try:
                user = db.users.find_one({"email": email})
            except Exception as e:
                print(f"⚠️ Direct query failed: {e}")
            
            # Method 2: Manual search for in-memory database
            if not user:
                try:
                    all_users = list(db.users.find({}))
                    for u in all_users:
                        if u.get("email", "").lower() == email.lower():
                            user = u
                            break
                except Exception as e:
                    print(f"⚠️ Manual search failed: {e}")
            
            print(f"🔍 User lookup result: {'Found' if user else 'Not found'}")
            
            if not user:
                # Show all registered emails for debugging (remove in production)
                try:
                    all_users = list(db.users.find({}, {"email": 1, "username": 1, "_id": 0}))
                    registered_emails = [u.get("email") for u in all_users if u.get("email")]
                    print(f"📧 Registered emails: {registered_emails}")
                    
                    if not registered_emails:
                        error = "No users are registered yet. Please register first."
                    else:
                        error = f"No account found with email '{email}'. Registered emails: {', '.join(registered_emails[:3])}..."
                except:
                    error = "No account found with this email address"
                
                return render_template("forgot_password.html", error=error)
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            error = f"Database error: {str(e)}"
            return render_template("forgot_password.html", error=error)
        
        # Generate reset token
        try:
            reset_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
            
            # Store reset token in database (expires in 1 hour)
            reset_record = {
                "email": email,
                "username": user["username"],
                "token_hash": token_hash,
                "expires_at": datetime.datetime.now() + datetime.timedelta(hours=1),
                "used": False,
                "created_at": datetime.datetime.now()
            }
            
            db.password_resets.insert_one(reset_record)
            print(f"✅ Reset token created for {email}")
            
        except Exception as e:
            print(f"❌ Token creation error: {e}")
            error = f"Failed to create reset token: {str(e)}"
            return render_template("forgot_password.html", error=error)
        
        # Create reset link
        reset_link = f"http://127.0.0.1:5000/reset-password/{reset_token}"
        
        try:
            # Send email using Flask-Mail
            msg = Message(
                subject="Password Reset Request - Smart Attendance",
                recipients=[email],
                html=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
                        <h1 style="color: white; margin: 0;">Smart Attendance System</h1>
                    </div>
                    
                    <div style="padding: 30px; background: #f8f9fa;">
                        <h2 style="color: #333; margin-bottom: 20px;">Password Reset Request</h2>
                        
                        <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                            Hello <strong>{user['username']}</strong>,
                        </p>
                        
                        <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                            We received a request to reset your password for your Smart Attendance account. 
                            If you made this request, click the button below to reset your password:
                        </p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_link}" 
                               style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                      color: white; 
                                      padding: 12px 30px; 
                                      text-decoration: none; 
                                      border-radius: 6px; 
                                      font-weight: bold;
                                      display: inline-block;">
                                Reset My Password
                            </a>
                        </div>
                        
                        <p style="color: #666; line-height: 1.6; margin-bottom: 10px;">
                            Or copy and paste this link into your browser:
                        </p>
                        <p style="color: #007bff; word-break: break-all; margin-bottom: 20px;">
                            {reset_link}
                        </p>
                        
                        <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 6px; margin: 20px 0;">
                            <p style="color: #856404; margin: 0; font-size: 14px;">
                                <strong>Security Note:</strong> This link will expire in 1 hour. 
                                If you didn't request this password reset, please ignore this email.
                            </p>
                        </div>
                        
                        <p style="color: #666; line-height: 1.6; margin-top: 30px;">
                            Best regards,<br>
                            Smart Attendance Team
                        </p>
                    </div>
                    
                    <div style="background: #343a40; padding: 20px; text-align: center;">
                        <p style="color: #adb5bd; margin: 0; font-size: 12px;">
                            © 2024 Smart Attendance System. This is an automated message.
                        </p>
                    </div>
                </div>
                """
            )
            
            mail.send(msg)
            print(f"✅ Reset email sent to {email}")
            success = "Reset link sent to your email! Please check your inbox and spam folder."
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            error = f"Failed to send email: {str(e)}. Please check SMTP configuration."
            return render_template("forgot_password.html", error=error)
        
        return render_template("forgot_password.html", success=success)
    
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    # Verify token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    reset_request = db.password_resets.find_one({
        "token_hash": token_hash,
        "used": False,
        "expires_at": {"$gt": datetime.datetime.now()}
    })
    
    if not reset_request:
        return render_template("reset_password.html", 
                             invalid_token="Invalid or expired reset link")
    
    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        
        # Validate passwords match
        if password != confirm_password:
            return render_template("reset_password.html", 
                                 error="Passwords do not match")
        
        # Update user password using email
        hashed_pwd = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        
        db.users.update_one(
            {"email": reset_request["email"]},
            {"$set": {"password": hashed_pwd}}
        )
        
        # Mark token as used
        db.password_resets.update_one(
            {"_id": reset_request["_id"]},
            {"$set": {"used": True}}
        )
        
        success = "Password reset successfully! You can now login with your new password."
        return render_template("reset_password.html", success=success)
    
    return render_template("reset_password.html")
