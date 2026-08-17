import pandas as pd
from flask import Flask, send_file, render_template, jsonify
from flask_mail import Mail
from pyngrok import ngrok
import os
import io
from db import db
#from attendance import generate_graphs

app = Flask(__name__)
app.secret_key = "attendance_secret"

# ✅ Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = "dsmithu2005@gmail.com"  # Updated email
app.config['MAIL_PASSWORD'] = "kdytpwiydsvrcdfx"  # Updated app password
app.config['MAIL_DEFAULT_SENDER'] = "dsm05@gmail.com"  # Updated sender 

# ✅ Initialize Flask-Mail
mail = Mail()
mail.init_app(app)

# ✅ Import blueprints
from auth import auth_bp, init_mail
from qr import qr_bp
from attendance import attendance_bp

# ✅ Initialize mail in auth module
init_mail(mail)

# ✅ Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(qr_bp)
app.register_blueprint(attendance_bp)

# =========================
# ✅ EXPORT CSV ROUTE
# =========================
@app.route("/export_csv")
def export_csv():
    try:
        print("🔍 Starting CSV export...")
        
        # Get all attendance records
        records = list(db.attendance.find({}, {"_id": 0}))
        print(f"🔍 Found {len(records)} attendance records")
        
        # If no records, return error message
        if not records:
            print("⚠️ No attendance records found in database")
            return jsonify({
                "success": False,
                "message": "No attendance data found",
                "instructions": "Please mark attendance first before exporting"
            }), 404

        # Format records for CSV export
        formatted_records = []
        for record in records:
            location = record.get("location", {})
            
            formatted_record = {
                'Student Name': record.get("student", "Unknown"),
                'Session ID': record.get("session", record.get("session_id", "Unknown")),
                'Date': record.get("time_str", "Unknown").split(" ")[0] if record.get("time_str") else "Unknown",
                'Time': record.get("time_str", "Unknown").split(" ")[1] if record.get("time_str") and " " in record.get("time_str", "") else "Unknown",
                'Latitude': location.get("latitude", "N/A"),
                'Longitude': location.get("longitude", "N/A"),
                'Zone': location.get("primary_zone", "Unknown"),
                'Distance (m)': location.get("distance_from_zone", "N/A"),
                'GPS Accuracy (m)': location.get("accuracy", "N/A"),
                'Geofence Validated': location.get("geofence_validated", False),
                'IP Address': record.get("metadata", {}).get("ip_address", "N/A"),
                'User Agent': record.get("metadata", {}).get("user_agent", "N/A")
            }
            formatted_records.append(formatted_record)

        # Create DataFrame
        df = pd.DataFrame(formatted_records)
        
        # Generate CSV in-memory using StringIO
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        # Convert to BytesIO for send_file
        bytes_buffer = io.BytesIO()
        bytes_buffer.write(csv_buffer.getvalue().encode('utf-8'))
        bytes_buffer.seek(0)
        
        print(f"✅ CSV exported successfully with {len(formatted_records)} records")
        
        # Return CSV file directly from memory
        return send_file(
            bytes_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name="attendance.csv"
        )
        
    except Exception as e:
        print(f"❌ Error in CSV export: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# =========================
# ✅ MATLAB ANALYSIS PAGE
# =========================
from attendance import generate_graphs
@app.route("/analysis")
def analysis():
    # Get only student usernames (exclude admin)
    students = list(db.users.find({"role": "student"}, {"username": 1, "_id": 0}))
    
    # Extract student usernames into list
    student_names = [s["username"] for s in students]
    
    # Filter attendance records - only show student attendance (exclude admin)
    if student_names:
        attendance_records = list(db.attendance.find(
            {"student": {"$in": student_names}}, 
            {"_id": 0}
        ))
    else:
        attendance_records = []
    
    # Debug logging
    print(f"🔍 Students: {len(students)} registered")
    print(f"🔍 Student names: {student_names}")
    print(f"🔍 Attendance: {len(attendance_records)} records (students only)")
    
    # Determine message based on what's missing
    message = None
    if not students:
        message = "No students registered. Please register students first."
        print("⚠️ No students registered")
    elif not attendance_records:
        message = "No attendance data available. Please mark attendance first."
        print("⚠️ No attendance data for students")
    else:
        # Generate graphs only if we have both students and attendance
        generate_graphs()
        print("✅ Graphs generated successfully (students only)")
    
    return render_template("analysis.html", 
                         students=students, 
                         attendance=attendance_records,
                         message=message)

# =========================
# ✅ RUN SERVER
# =========================
if __name__ == "__main__":
    
    ngrok.set_auth_token("3BO1BlBMslpfVpSI9m7o67f07ON_3cxxu2Sptw17ntn1Gypx")
    ngrok.kill()
    
    print("🚀 Starting Smart Attendance System...")
    print("=" * 50)
    
    try:
        # ✅ Create ngrok tunnel for external access
        print("📡 Creating ngrok tunnel...")
        public_url = ngrok.connect(5000)
        print(public_url)
        print(f"✅ Public URL: {public_url}")
        print(f"🌐 External Access: {public_url}")
        print(f"🏠 Local Access: http://127.0.0.1:5000")
        print("=" * 50)
        print("📱 Share the public URL to access from other devices!")
        print("⚠️  Note: Free ngrok tunnels expire after 2 hours")
        print("=" * 50)
        
    except Exception as e:
        print(f"⚠️  ngrok tunnel creation failed: {e}")
        print("🔧 Running in local-only mode...")
        print(f"🏠 Local Access: http://127.0.0.1:5000")
        print("=" * 50)
    
    # ✅ Start Flask application
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        # ✅ Disconnect ngrok tunnel on shutdown
        try:
            ngrok.disconnect(public_url)
            print("✅ ngrok tunnel disconnected")
        except:
            pass
        print("👋 Server stopped successfully!")
# =========================
# ✅ TEST CSV EXPORT
# =========================
@app.route("/test_csv_export")
def test_csv_export():
    """Test endpoint to create sample data and test CSV export"""
    try:
        from attendance import get_ist_time
        import datetime
        
        # Check current records
        existing_records = list(db.attendance.find({}, {"_id": 0}))
        
        # If no records exist, create sample data
        if not existing_records:
            print("📝 Creating sample attendance data for CSV export test...")
            
            sample_students = ["John Doe", "Jane Smith", "Alice Johnson", "Bob Wilson", "Carol Brown"]
            
            for i, student in enumerate(sample_students):
                ist_time = get_ist_time()
                
                sample_record = {
                    "student": student,
                    "student_id": student,
                    "session": f"SESSION_TEST_{i+1}",
                    "session_id": f"SESSION_TEST_{i+1}",
                    "time": ist_time,
                    "time_str": ist_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "location": {
                        "latitude": 17.52723710588141 + (i * 0.001),
                        "longitude": 78.37139375341242 + (i * 0.001),
                        "accuracy": 15.0 + (i * 5),
                        "primary_zone": ["Main Campus", "Library", "Hostel"][i % 3],
                        "distance_from_zone": 50 + (i * 20),
                        "geofence_validated": True,
                        "security_checks": {
                            "cooldown_passed": True,
                            "accuracy_valid": True,
                            "spoofing_detected": False
                        }
                    },
                    "metadata": {
                        "ip_address": f"192.168.1.{100 + i}",
                        "user_agent": "Mozilla/5.0 (Test Browser)",
                        "timestamp_utc": datetime.datetime.utcnow()
                    }
                }
                
                db.attendance.insert_one(sample_record)
            
            print(f"✅ Created {len(sample_students)} sample attendance records")
        
        # Get updated record count
        all_records = list(db.attendance.find({}, {"_id": 0}))
        
        return {
            "success": True,
            "message": "Sample data created for CSV export test",
            "total_records": len(all_records),
            "sample_records": all_records[:3] if all_records else [],
            "instructions": [
                f"✅ {len(all_records)} attendance records available",
                "📊 Click 'Export CSV' button to download attendance data",
                "📁 CSV will contain: Student Name, Session ID, Date, Time, Location, etc.",
                "🔗 Direct CSV download: /export_csv"
            ]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }, 500
@app.route("/debug_csv")
def debug_csv():
    """Debug endpoint to check attendance data for CSV export"""
    try:
        # Get all records
        records = list(db.attendance.find({}, {"_id": 0}))
        
        # Sample formatted record
        sample_formatted = None
        if records:
            record = records[0]
            location = record.get("location", {})
            
            sample_formatted = {
                'Student Name': record.get("student", "Unknown"),
                'Session ID': record.get("session", record.get("session_id", "Unknown")),
                'Date': record.get("time_str", "Unknown").split(" ")[0] if record.get("time_str") else "Unknown",
                'Time': record.get("time_str", "Unknown").split(" ")[1] if record.get("time_str") and " " in record.get("time_str", "") else "Unknown",
                'Latitude': location.get("latitude", "N/A"),
                'Longitude': location.get("longitude", "N/A"),
                'Zone': location.get("primary_zone", "Unknown"),
                'Distance (m)': location.get("distance_from_zone", "N/A")
            }
        
        return {
            "database_status": {
                "total_records": len(records),
                "has_data": len(records) > 0
            },
            "sample_raw_record": records[0] if records else None,
            "sample_formatted_record": sample_formatted,
            "csv_columns": [
                'Student Name', 'Session ID', 'Date', 'Time', 
                'Latitude', 'Longitude', 'Zone', 'Distance (m)',
                'GPS Accuracy (m)', 'Geofence Validated', 'IP Address', 'User Agent'
            ],
            "instructions": [
                "🔍 This shows the current state of attendance data",
                "📊 If total_records = 0, visit /test_csv_export first",
                "📁 Then try /export_csv to download the CSV file",
                "✅ CSV should contain properly formatted attendance data"
            ]
        }
        
    except Exception as e:
        return {
            "error": str(e)
        }, 500
@app.route("/test_email")
def test_email():
    """Test email configuration"""
    try:
        from flask_mail import Message
        
        msg = Message(
            subject="Test Email - Smart Attendance System",
            recipients=["dsm05@gmail.com"],  # Send to the configured email
            body="This is a test email to verify SMTP configuration is working correctly."
        )
        
        mail.send(msg)
        
        return {
            "success": True,
            "message": "Test email sent successfully",
            "smtp_config": {
                "server": app.config['MAIL_SERVER'],
                "port": app.config['MAIL_PORT'],
                "username": app.config['MAIL_USERNAME'],
                "sender": app.config['MAIL_DEFAULT_SENDER']
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "smtp_config": {
                "server": app.config['MAIL_SERVER'],
                "port": app.config['MAIL_PORT'],
                "username": app.config['MAIL_USERNAME'],
                "sender": app.config['MAIL_DEFAULT_SENDER']
            }
        }, 500
@app.route("/debug_forgot_password")
def debug_forgot_password():
    """Debug endpoint to check forgot password functionality"""
    try:
        # Check registered users
        all_users = list(db.users.find({}, {"username": 1, "email": 1, "role": 1, "_id": 0}))
        
        # Check SMTP configuration
        smtp_config = {
            "server": app.config.get('MAIL_SERVER'),
            "port": app.config.get('MAIL_PORT'),
            "username": app.config.get('MAIL_USERNAME'),
            "sender": app.config.get('MAIL_DEFAULT_SENDER'),
            "tls": app.config.get('MAIL_USE_TLS')
        }
        
        # Check password reset collection
        try:
            reset_tokens = list(db.password_resets.find({}, {"email": 1, "expires_at": 1, "used": 1, "_id": 0}))
        except:
            reset_tokens = []
        
        return jsonify({
            "debug_info": {
                "registered_users": {
                    "count": len(all_users),
                    "users": all_users
                },
                "smtp_configuration": smtp_config,
                "password_resets": {
                    "count": len(reset_tokens),
                    "recent_tokens": reset_tokens[-5:] if reset_tokens else []
                }
            },
            "test_instructions": [
                "1. Ensure users are registered with valid email addresses",
                "2. Use registered email addresses in forgot password form",
                "3. Check SMTP configuration is correct",
                "4. Test with /test_forgot_password_email endpoint"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route("/test_forgot_password_email")
def test_forgot_password_email():
    """Test forgot password with a known email"""
    try:
        # Get first registered user
        user = db.users.find_one({"role": "student"})
        
        if not user:
            return jsonify({
                "error": "No registered users found",
                "message": "Register a user first via /register"
            })
        
        test_email = user.get("email")
        username = user.get("username")
        
        if not test_email:
            return jsonify({
                "error": "User has no email address",
                "username": username
            })
        
        # Test the forgot password process
        from flask_mail import Message
        import secrets
        import hashlib
        import datetime
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        
        # Store reset token
        db.password_resets.insert_one({
            "email": test_email,
            "username": username,
            "token_hash": token_hash,
            "expires_at": datetime.datetime.now() + datetime.timedelta(hours=1),
            "used": False
        })
        
        # Create reset link
        reset_link = f"http://127.0.0.1:5000/reset-password/{reset_token}"
        
        # Send test email
        msg = Message(
            subject="Test Password Reset - Smart Attendance",
            recipients=[test_email],
            html=f"""
            <h2>Test Password Reset</h2>
            <p>Hello {username},</p>
            <p>This is a test email for password reset functionality.</p>
            <p><a href="{reset_link}">Reset Password</a></p>
            <p>Reset Link: {reset_link}</p>
            """
        )
        
        mail.send(msg)
        
        return jsonify({
            "success": True,
            "message": "Test email sent successfully",
            "test_details": {
                "email": test_email,
                "username": username,
                "reset_link": reset_link,
                "token": reset_token
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
