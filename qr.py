import qrcode
import datetime
import pytz
from flask import Blueprint, render_template, session, jsonify, request, redirect, url_for
from db import db

qr_bp = Blueprint("qr", __name__)   # ✅ FIXED

def validate_session():
    """Validate if current session is still active in database"""
    from auth import validate_session as auth_validate_session
    return auth_validate_session()

def require_valid_session():
    """Require valid session for students"""
    if session.get("role") == "student" and not validate_session():
        session.clear()
        return redirect("/?error=session_expired")
    return None

def require_admin():
    """Decorator function to require admin role"""
    if not session.get("role") == "admin":
        return False
    return True

def admin_required_response():
    """Return appropriate response for non-admin users"""
    return render_template("unauthorized.html", 
                         message="Only admin can create attendance sessions"), 403

@qr_bp.route("/create_qr", methods=["GET", "POST"])
def create_qr():
    # ✅ Admin-only access control
    if not require_admin():
        return admin_required_response()

    login_time_str = session.get("admin_login_time")
    if not login_time_str:
        return "❌ Admin session expired. Please login again."

    # Create new session with 2 minutes expiry (120 seconds)
    session_id = "SESSION_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    created_at = datetime.datetime.now()
    expires_at = created_at + datetime.timedelta(seconds=120)  # 2 minutes

    # Store session with more details
    session_data = {
        "session_id": session_id,
        "created_at": created_at,
        "expires_at": expires_at,
        "admin_id": session.get("username", "admin"),
        "is_active": True,
        "attendees": [],
        "attendee_count": 0
    }
    
    db.sessions.insert_one(session_data)

    # Generate QR code
    img = qrcode.make(session_id)
    img.save("static/qr.png")

    role = session.get("role", "guest")
    return render_template(
        "show_qr.html",
        session_id=session_id,
        created_at=created_at,
        expires_at=expires_at,
        role=role
    )


@qr_bp.route("/generate_qr", methods=["GET", "POST"])
def generate_qr():
    """Alternative route name for QR generation"""
    # ✅ Admin-only access control
    if not require_admin():
        return admin_required_response()
    
    return create_qr()


@qr_bp.route("/create_session", methods=["GET", "POST"])
def create_session():
    """Alternative route name for session creation"""
    # ✅ Admin-only access control
    if not require_admin():
        return admin_required_response()
    
    return create_qr()


@qr_bp.route("/current_session")
def get_current_session():
    """API endpoint to get the current active session"""
    # Validate session for students
    validation_result = require_valid_session()
    if validation_result:
        return validation_result
    
    try:
        # Find the most recent session that hasn't expired
        current_time = datetime.datetime.now()
        
        # Get all sessions and filter manually (works with both MongoDB and in-memory)
        all_sessions = list(db.sessions.find({}))
        
        # Filter active sessions manually
        active_sessions = []
        for session_data in all_sessions:
            expires_at = session_data.get("expires_at")
            if expires_at and expires_at > current_time:
                active_sessions.append(session_data)
        
        if not active_sessions:
            print(f"🔍 No active sessions found. Current time: {current_time}")
            print(f"🔍 Total sessions in DB: {len(all_sessions)}")
            for s in all_sessions[-3:]:  # Show last 3 sessions for debugging
                print(f"   Session: {s.get('session_id', 'Unknown')} expires at {s.get('expires_at', 'Unknown')}")
            
            return jsonify({
                "success": False,
                "message": "No active session available",
                "debug": {
                    "current_time": current_time.isoformat(),
                    "total_sessions": len(all_sessions),
                    "recent_sessions": [
                        {
                            "session_id": s.get("session_id", "Unknown"),
                            "expires_at": s.get("expires_at").isoformat() if s.get("expires_at") else "Unknown"
                        } for s in all_sessions[-2:]
                    ]
                }
            })
        
        # Get the most recent active session
        active_session = max(active_sessions, key=lambda x: x.get("created_at", datetime.datetime.min))
        
        # Calculate remaining time in seconds
        remaining_time = (active_session["expires_at"] - current_time).total_seconds()
        
        print(f"✅ Active session found: {active_session['session_id']}, Remaining: {remaining_time}s")
        
        return jsonify({
            "success": True,
            "session_id": active_session["session_id"],
            "expires_at": active_session["expires_at"].isoformat(),
            "remaining_seconds": max(0, int(remaining_time))
        })
        
    except Exception as e:
        print(f"❌ Error in get_current_session: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


@qr_bp.route("/refresh_qr")
def refresh_qr():
    """API endpoint to create a new QR session (2 minutes expiry)"""
    try:
        # Create new session with 2 minutes expiry (120 seconds)
        session_id = "SESSION_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        created_at = datetime.datetime.now()
        expires_at = created_at + datetime.timedelta(seconds=120)
        
        session_data = {
            "session_id": session_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "admin_id": session.get("username", "admin"),
            "is_active": True,
            "attendees": [],
            "attendee_count": 0
        }
        
        db.sessions.insert_one(session_data)
        
        # Generate new QR code
        img = qrcode.make(session_id)
        img.save("static/qr.png")
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "remaining_seconds": 120  # 2 minutes
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500
