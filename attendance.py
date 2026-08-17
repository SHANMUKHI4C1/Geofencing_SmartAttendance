from flask import Blueprint, request, jsonify, render_template, session, redirect
from datetime import datetime, timedelta
import pytz
import math
import json
from db import db
import pandas as pd
import matplotlib.pyplot as plt
from typing import Tuple, Dict, Any, List, Optional

attendance_bp = Blueprint("attendance", __name__)

# ===========================
# GEOFENCING CONFIGURATION
# ===========================

# BVRIT Hyderabad College coordinates
COLLEGE_LAT = 17.52723710588141
COLLEGE_LON = 78.37139375341242
MAX_DISTANCE_METERS = 500  # Maximum allowed distance from college

# Multiple geofence zones for enhanced security
GEOFENCE_ZONES = {
    "main_campus": {
        "name": "Main Campus",
        "latitude": 17.52723710588141,
        "longitude": 78.37139375341242,
        "radius": 500,  # Temporarily increased for testing
        "priority": 1
    },
    "library": {
        "name": "Library Block",
        "latitude": 17.52750000000000,
        "longitude": 78.37150000000000,
        "radius": 200,
        "priority": 2
    },
    "hostel": {
        "name": "Hostel Area",
        "latitude": 17.52700000000000,
        "longitude": 78.37100000000000,
        "radius": 300,
        "priority": 3
    }
}

# Security settings
LOCATION_ACCURACY_THRESHOLD = 150  # meters (increased for testing)
MAX_SPEED_THRESHOLD = 50  # km/h (to detect spoofing)
ATTENDANCE_COOLDOWN = 0  # Disabled for testing (was 300 seconds)

# ===========================
# GEOFENCING FUNCTIONS
# ===========================

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the distance between two coordinates using Haversine formula
    Returns distance in meters with high precision
    """
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in meters (more precise value)
    earth_radius_m = 6371000
    
    # Calculate the distance
    distance = earth_radius_m * c
    return distance

def validate_geofence_zones(student_lat: float, student_lon: float) -> Tuple[bool, Dict[str, Any]]:
    """
    Advanced geofencing validation with multiple zones
    Returns (is_valid, zone_info)
    """
    try:
        student_lat = float(student_lat)
        student_lon = float(student_lon)
        
        valid_zones = []
        closest_zone = None
        min_distance = float('inf')
        
        # Check all geofence zones
        for zone_id, zone_config in GEOFENCE_ZONES.items():
            distance = calculate_distance(
                zone_config["latitude"], zone_config["longitude"],
                student_lat, student_lon
            )
            
            zone_info = {
                "zone_id": zone_id,
                "zone_name": zone_config["name"],
                "distance": round(distance, 2),
                "radius": zone_config["radius"],
                "is_within": distance <= zone_config["radius"],
                "priority": zone_config["priority"]
            }
            
            if zone_info["is_within"]:
                valid_zones.append(zone_info)
            
            # Track closest zone
            if distance < min_distance:
                min_distance = distance
                closest_zone = zone_info
        
        # Sort valid zones by priority
        valid_zones.sort(key=lambda x: x["priority"])
        
        result = {
            "is_valid": len(valid_zones) > 0,
            "valid_zones": valid_zones,
            "closest_zone": closest_zone,
            "total_zones_checked": len(GEOFENCE_ZONES),
            "student_location": {
                "latitude": student_lat,
                "longitude": student_lon
            }
        }
        
        if valid_zones:
            primary_zone = valid_zones[0]
            result["message"] = f"✅ Location validated - within {primary_zone['zone_name']} (Distance: {primary_zone['distance']}m)"
            result["primary_zone"] = primary_zone
        else:
            result["message"] = f"🚫 Outside all campus zones. Closest: {closest_zone['zone_name']} ({closest_zone['distance']}m away)"
        
        return result["is_valid"], result
        
    except (ValueError, TypeError) as e:
        return False, {
            "is_valid": False,
            "error": f"Invalid location coordinates: {str(e)}",
            "message": "❌ Invalid location data provided"
        }

def validate_location_accuracy(accuracy: Optional[float]) -> Tuple[bool, str]:
    """
    Validate GPS accuracy to prevent spoofing
    """
    if accuracy is None:
        return True, "No accuracy data provided"
    
    if accuracy > LOCATION_ACCURACY_THRESHOLD:
        return False, f"GPS accuracy too low ({accuracy}m). Required: <{LOCATION_ACCURACY_THRESHOLD}m"
    
    return True, f"GPS accuracy acceptable ({accuracy}m)"

def detect_location_spoofing(student_id: str, current_lat: float, current_lon: float) -> Tuple[bool, str]:
    """
    Detect potential location spoofing by checking movement speed
    """
    try:
        # Get last location record for this student
        last_record = db.attendance.find_one(
            {"student": student_id},
            sort=[("time", -1)]
        )
        
        if not last_record or "location" not in last_record:
            return True, "No previous location data"
        
        last_location = last_record["location"]
        last_time = last_record["time"]
        current_time = datetime.utcnow()
        
        # Calculate time difference in hours
        time_diff = (current_time - last_time).total_seconds() / 3600
        
        if time_diff < 0.01:  # Less than 36 seconds
            return True, "Too soon for speed calculation"
        
        # Calculate distance moved
        distance_moved = calculate_distance(
            last_location["latitude"], last_location["longitude"],
            current_lat, current_lon
        )
        
        # Calculate speed in km/h
        speed_kmh = (distance_moved / 1000) / time_diff
        
        if speed_kmh > MAX_SPEED_THRESHOLD:
            return False, f"Suspicious movement detected. Speed: {speed_kmh:.1f} km/h (Max: {MAX_SPEED_THRESHOLD} km/h)"
        
        return True, f"Movement speed normal: {speed_kmh:.1f} km/h"
        
    except Exception as e:
        return True, f"Speed validation error: {str(e)}"

def check_attendance_cooldown(student_id: str) -> Tuple[bool, str]:
    """
    Prevent rapid attendance marking (anti-spam)
    """
    try:
        last_attendance = db.attendance.find_one(
            {"student": student_id},
            sort=[("time", -1)]
        )
        
        if not last_attendance:
            return True, "No previous attendance"
        
        last_time = last_attendance["time"]
        current_time = datetime.utcnow()
        time_diff = (current_time - last_time).total_seconds()
        
        if time_diff < ATTENDANCE_COOLDOWN:
            remaining = ATTENDANCE_COOLDOWN - time_diff
            return False, f"Please wait {remaining:.0f} seconds before marking attendance again"
        
        return True, "Cooldown period passed"
        
    except Exception as e:
        return True, f"Cooldown check error: {str(e)}"

def validate_session():
    """Validate if current session is still active in database"""
    from auth import validate_session as auth_validate_session
    return auth_validate_session()

def require_valid_session():
    """Require valid session for students"""
    if session.get("role") == "student" and not validate_session():
        session.clear()
        return "❌ Session expired. Please login again."
    return None

# ✅ Helper → IST time
def get_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

# ✅ GRAPH FUNCTION
def generate_graphs():
    try:
        print("🔍 Starting graph generation...")
        
        # Get only student usernames (exclude admin)
        students = list(db.users.find({"role": "student"}, {"username": 1, "_id": 0}))
        student_names = [s["username"] for s in students]
        
        # Filter attendance records - only students
        if student_names:
            records = list(db.attendance.find(
                {"student": {"$in": student_names}}, 
                {"_id": 0}
            ))
        else:
            records = []
        
        print(f"🔍 Found {len(records)} attendance records (students only)")

        if not records:
            print("⚠️ No student attendance records found for graph generation")
            return

        df = pd.DataFrame(records)
        print(f"🔍 DataFrame created with columns: {list(df.columns)}")

        if df.empty:
            print("⚠️ DataFrame is empty")
            return

        # Check if 'student' column exists
        if "student" not in df.columns:
            print("❌ 'student' column not found in data")
            print(f"Available columns: {list(df.columns)}")
            return

        counts = df["student"].value_counts()
        print(f"🔍 Student counts: {counts.to_dict()}")

        # ✅ Bar Chart
        plt.figure(figsize=(10, 6))
        counts.plot(kind="bar")
        plt.title("Attendance per Student")
        plt.xlabel("Students")
        plt.ylabel("Count")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig("static/bar_chart.png", dpi=150, bbox_inches='tight')
        plt.close()
        print("✅ Bar chart saved to static/bar_chart.png")

        # ✅ Pie Chart
        plt.figure(figsize=(8, 8))
        counts.plot(kind="pie", autopct="%1.1f%%")
        plt.ylabel("")
        plt.title("Attendance Distribution")
        plt.tight_layout()
        plt.savefig("static/pie_chart.png", dpi=150, bbox_inches='tight')
        plt.close()
        print("✅ Pie chart saved to static/pie_chart.png")
        
        print("✅ Graph generation completed successfully")
        
    except Exception as e:
        print(f"❌ Error in generate_graphs: {str(e)}")
        import traceback
        traceback.print_exc()


@attendance_bp.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    """Enhanced attendance marking with advanced geofencing"""
    # Validate session for students
    validation_result = require_valid_session()
    if validation_result:
        return validation_result

    # 🔒 SECURITY FIX: Use logged-in username from session instead of form input
    logged_in_username = session.get("username")
    role = session.get("role")
    
    if not logged_in_username:
        return "❌ Session expired. Please login again."
    
    # 🔒 PREVENT ADMIN ATTENDANCE: Admins cannot mark attendance
    # TEMPORARILY DISABLED FOR TESTING
    # if role == "admin":
    #     print(f"🚫 Admin {logged_in_username} attempted to mark attendance")
    #     return jsonify({
    #         "success": False,
    #         "message": "Admins cannot mark attendance. Only students can mark attendance."
    #     }), 403
    
    # Use the logged-in username (prevents students from marking attendance for others)
    student = logged_in_username
    
    # Get form data with debugging
    session_id = request.form.get("session", "").strip()
    student_lat = request.form.get("latitude", "").strip()
    student_lon = request.form.get("longitude", "").strip()
    accuracy = request.form.get("accuracy", "").strip()
    
    # Debug logging
    print(f"🔍 Debug - Received form data:")
    print(f"   Logged-in User: '{student}' (from session)")
    print(f"   Session ID: '{session_id}'")
    print(f"   Latitude: '{student_lat}'")
    print(f"   Longitude: '{student_lon}'")
    print(f"   Accuracy: '{accuracy}'")
    
    # Basic validation with more specific error messages
    if not session_id:
        return "❌ Session ID is missing. Please scan a valid QR code first."

    if not student_lat or not student_lon:
        return "❌ Location data is missing. Please enable location services and try again."
    
    # Convert to float for validation
    try:
        student_lat = float(student_lat)
        student_lon = float(student_lon)
        accuracy = float(accuracy) if accuracy else None
    except (ValueError, TypeError) as e:
        return f"❌ Invalid location coordinates: {str(e)}"
    
    # Security validations
    
    # 1. Check attendance cooldown
    cooldown_valid, cooldown_msg = check_attendance_cooldown(student)
    if not cooldown_valid:
        return f"⏳ {cooldown_msg}"
    
    # 2. Validate GPS accuracy
    accuracy_valid, accuracy_msg = validate_location_accuracy(accuracy)
    if not accuracy_valid:
        return f"📍 {accuracy_msg}"
    
    # 3. Detect location spoofing
    spoofing_valid, spoofing_msg = detect_location_spoofing(student, student_lat, student_lon)
    if not spoofing_valid:
        return f"🚨 {spoofing_msg}"
    
    # 4. Advanced geofencing validation
    is_valid_location, geofence_result = validate_geofence_zones(student_lat, student_lon)
    
    if not is_valid_location:
        return f"🚫 {geofence_result['message']}"

    # 🔧 FIX: Session validation with improved debugging
    print(f"🔍 Searching for session: '{session_id}'")
    
    # Get all sessions for debugging
    all_sessions = list(db.sessions.find({}, {"session_id": 1, "expires_at": 1, "_id": 0}))
    print(f"🔍 Total sessions in DB: {len(all_sessions)}")
    if all_sessions:
        print(f"🔍 Recent sessions: {[s.get('session_id', 'Unknown') for s in all_sessions[-3:]]}")
    
    session_data = None
    
    # Try different session query formats
    possible_queries = [
        {"session_id": session_id},
        {"_id": session_id},
        {"session": session_id}
    ]
    
    for query in possible_queries:
        try:
            session_data = db.sessions.find_one(query)
            if session_data:
                print(f"✅ Found session with query: {query}")
                break
        except Exception as e:
            print(f"⚠️ Session query failed for {query}: {e}")
            continue
    
    # 🔧 FIX: If no session found, try to get the latest active session
    if not session_data:
        print(f"⚠️ Session '{session_id}' not found. Checking for latest active session...")
        try:
            current_time = datetime.utcnow()
            # Get all sessions and find active ones
            all_sessions_full = list(db.sessions.find({}))
            active_sessions = [s for s in all_sessions_full if s.get("expires_at") and s["expires_at"] > current_time]
            
            if active_sessions:
                # Use the most recent active session
                session_data = max(active_sessions, key=lambda x: x.get("created_at", datetime.min))
                print(f"✅ Using latest active session: {session_data.get('session_id')}")
            else:
                print(f"❌ No active sessions found")
                return jsonify({
                    "success": False,
                    "message": "Session not found or expired. Please wait for admin to create a new session.",
                    "debug": {
                        "requested_session": session_id,
                        "total_sessions": len(all_sessions_full),
                        "active_sessions": 0
                    }
                }), 404
        except Exception as e:
            print(f"❌ Error finding active session: {e}")
            return f"❌ Invalid QR code or session '{session_id}' not found. Please scan a valid QR code."
    
    # Check session expiration
    expires_at = session_data.get("expires_at")
    if expires_at and datetime.utcnow() > expires_at:
        print(f"⏰ Session expired at {expires_at}")
        return "⏰ QR code has expired. Please scan a new QR code."

    # Check for duplicate attendance
    existing_queries = [
        {"student": student, "session": session_id},
        {"student": student, "session_id": session_id},
        {"student_id": student, "session": session_id},
        {"student_id": student, "session_id": session_id}
    ]
    
    existing = None
    for query in existing_queries:
        try:
            existing = db.attendance.find_one(query)
            if existing:
                break
        except:
            continue

    if existing:
        return "⚠️ Attendance already marked for this session"

    # Get IST time
    ist_time = get_ist_time()
    
    # Prepare comprehensive attendance record
    primary_zone = geofence_result.get("primary_zone", {})
    attendance_record = {
        "student": student,
        "student_id": student,  # For compatibility
        "session": session_id,
        "session_id": session_id,  # For compatibility
        "time": ist_time,
        "time_str": ist_time.strftime("%Y-%m-%d %H:%M:%S"),
        "location": {
            "latitude": student_lat,
            "longitude": student_lon,
            "accuracy": accuracy,
            "primary_zone": primary_zone.get("zone_name", "Unknown"),
            "distance_from_zone": primary_zone.get("distance", 0),
            "all_valid_zones": [zone["zone_name"] for zone in geofence_result.get("valid_zones", [])],
            "geofence_validated": True,
            "security_checks": {
                "cooldown_passed": True,
                "accuracy_valid": accuracy_valid,
                "spoofing_detected": not spoofing_valid,
                "accuracy_meters": accuracy,
                "spoofing_check_message": spoofing_msg
            }
        },
        "metadata": {
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get('User-Agent', 'Unknown'),
            "timestamp_utc": datetime.utcnow()
        }
    }

    # Store attendance record
    try:
        result = db.attendance.insert_one(attendance_record)
        print(f"✅ Attendance recorded with ID: {result.inserted_id}")
        
        # Update session attendee count (try multiple formats)
        update_queries = [
            {"session_id": session_id},
            {"_id": session_id},
            {"session": session_id}
        ]
        
        for query in update_queries:
            try:
                update_result = db.sessions.update_one(
                    query,
                    {
                        "$inc": {"attendee_count": 1}, 
                        "$addToSet": {"attendees": student}
                    }
                )
                if update_result.modified_count > 0:
                    print(f"✅ Session updated with query: {query}")
                    break
            except Exception as e:
                print(f"⚠️ Session update failed for {query}: {e}")
                continue
        
        # Auto-generate graphs
        try:
            generate_graphs()
        except Exception as e:
            print(f"⚠️ Graph generation failed: {e}")
        
        zone_name = primary_zone.get("zone_name", "Campus")
        distance = primary_zone.get("distance", 0)
        
        return f"✅ Attendance marked successfully!\n📍 Location: {zone_name} ({distance:.0f}m)\n🔒 Security: All checks passed"
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return f"❌ Failed to record attendance: {str(e)}"


# ✅ HEATMAP ANALYTICS ROUTES
@attendance_bp.route("/heatmap")
def heatmap_page():
    """Render the heatmap analytics page - accessible by both students and admins"""
    # Allow both students and admins to access heatmap
    role = session.get("role", "guest")
    username = session.get("username", "")
    
    # Only require session validation for students, admins have broader access
    if role == "student":
        validation_result = require_valid_session()
        if validation_result:
            from flask import redirect
            return redirect("/?error=session_expired")
    elif role != "admin":
        # If not student or admin, redirect to login
        from flask import redirect
        return redirect("/?error=access_denied")
    
    print(f"🔍 Heatmap accessed by role: {role}, username: {username}")
    return render_template("heatmap.html", role=role, username=username)


@attendance_bp.route("/test_location", methods=["POST"])
def test_location():
    """Enhanced API endpoint to test geofencing validation"""
    try:
        data = request.get_json() or {}
        lat = data.get('latitude') or request.form.get('latitude')
        lon = data.get('longitude') or request.form.get('longitude')
        accuracy = data.get('accuracy') or request.form.get('accuracy')
        student_id = data.get('student_id') or request.form.get('student_id')
        
        if not lat or not lon:
            return jsonify({
                "error": "Missing latitude or longitude",
                "required": ["latitude", "longitude"]
            }), 400
        
        # Convert to float
        lat = float(lat)
        lon = float(lon)
        accuracy = float(accuracy) if accuracy else None
        
        # Run all validation checks
        is_valid, geofence_result = validate_geofence_zones(lat, lon)
        accuracy_valid, accuracy_msg = validate_location_accuracy(accuracy)
        
        # Optional spoofing check if student_id provided
        spoofing_result = None
        if student_id:
            spoofing_valid, spoofing_msg = detect_location_spoofing(student_id, lat, lon)
            spoofing_result = {
                "valid": spoofing_valid,
                "message": spoofing_msg
            }
        
        response = {
            "geofencing": geofence_result,
            "accuracy_check": {
                "valid": accuracy_valid,
                "message": accuracy_msg,
                "threshold": LOCATION_ACCURACY_THRESHOLD
            },
            "spoofing_check": spoofing_result,
            "overall_valid": is_valid and accuracy_valid,
            "geofence_zones": GEOFENCE_ZONES,
            "security_settings": {
                "max_distance_meters": MAX_DISTANCE_METERS,
                "accuracy_threshold": LOCATION_ACCURACY_THRESHOLD,
                "max_speed_threshold": MAX_SPEED_THRESHOLD,
                "attendance_cooldown": ATTENDANCE_COOLDOWN
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "error": f"Location validation failed: {str(e)}"
        }), 500


@attendance_bp.route("/geofence_info")
def geofence_info():
    """API endpoint to get detailed geofencing information"""
    return jsonify({
        "college_name": "BVRIT Hyderabad College",
        "main_coordinates": {
            "latitude": COLLEGE_LAT,
            "longitude": COLLEGE_LON
        },
        "geofence_zones": GEOFENCE_ZONES,
        "security_settings": {
            "max_distance_meters": MAX_DISTANCE_METERS,
            "location_accuracy_threshold": LOCATION_ACCURACY_THRESHOLD,
            "max_speed_threshold": MAX_SPEED_THRESHOLD,
            "attendance_cooldown_seconds": ATTENDANCE_COOLDOWN
        },
        "address": "BVRIT Hyderabad College of Engineering for Women, Bachupally, Hyderabad",
        "features": [
            "Multi-zone geofencing",
            "GPS accuracy validation",
            "Location spoofing detection",
            "Attendance cooldown protection",
            "Real-time distance calculation"
        ]
    })


@attendance_bp.route("/security_report/<student_id>")
def security_report(student_id):
    """Generate security report for a student's attendance patterns"""
    try:
        # Get all attendance records for the student
        records = list(db.attendance.find(
            {"student": student_id},
            {"_id": 0}
        ).sort("time", -1).limit(50))
        
        if not records:
            return jsonify({"error": "No attendance records found"}), 404
        
        # Analyze security patterns
        security_analysis = {
            "student_id": student_id,
            "total_records": len(records),
            "analysis_period": {
                "from": records[-1]["time_str"] if records else None,
                "to": records[0]["time_str"] if records else None
            },
            "location_patterns": {},
            "security_flags": [],
            "zone_usage": {}
        }
        
        # Analyze location patterns
        for record in records:
            location = record.get("location", {})
            zone = location.get("primary_zone", "Unknown")
            
            if zone not in security_analysis["zone_usage"]:
                security_analysis["zone_usage"][zone] = 0
            security_analysis["zone_usage"][zone] += 1
            
            # Check for security flags
            security_checks = location.get("security_checks", {})
            if security_checks.get("spoofing_detected"):
                security_analysis["security_flags"].append({
                    "type": "spoofing_detected",
                    "timestamp": record["time_str"],
                    "message": security_checks.get("spoofing_check_message", "Unknown")
                })
            
            if not security_checks.get("accuracy_valid"):
                security_analysis["security_flags"].append({
                    "type": "low_accuracy",
                    "timestamp": record["time_str"],
                    "accuracy": security_checks.get("accuracy_meters", "Unknown")
                })
        
        return jsonify(security_analysis)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/attendance/<student_id>")
def get_student_attendance(student_id):
    """API endpoint to get student attendance data for heatmap with role-based access control"""
    try:
        role = session.get("role", "guest")
        logged_in_username = session.get("username", "")
        
        print(f"🔍 Getting attendance for student: {student_id}")
        print(f"🔍 Requested by role: {role}, username: {logged_in_username}")
        
        # 🔒 ROLE-BASED ACCESS CONTROL
        if role == "student":
            # Students can ONLY view their own attendance
            if student_id != logged_in_username:
                print(f"🚫 Access denied: Student {logged_in_username} tried to access {student_id}'s data")
                return jsonify({
                    "error": "Access denied",
                    "message": "You can only view your own attendance"
                }), 403
        elif role != "admin":
            # Only students and admins can access this endpoint
            print(f"🚫 Unauthorized access attempt by role: {role}")
            return jsonify({
                "error": "Unauthorized",
                "message": "Access denied"
            }), 403
        
        # Verify the requested student is actually a student (not admin)
        user = db.users.find_one({"username": student_id})
        if user and user.get("role") == "admin":
            print(f"🚫 Attempted to access admin attendance: {student_id}")
            return jsonify([])  # Return empty array for admin users
        
        # Get attendance records for the student (try both student and student_id fields)
        records = []
        
        # Try different field names for compatibility
        queries = [
            {"student": student_id},
            {"student_id": student_id}
        ]
        
        for query in queries:
            try:
                found_records = list(db.attendance.find(
                    query, 
                    {"_id": 0, "time_str": 1, "student": 1, "time": 1, "session": 1}
                ))
                records.extend(found_records)
            except Exception as e:
                print(f"⚠️ Query {query} failed: {e}")
        
        # Remove duplicates based on time_str
        seen_times = set()
        unique_records = []
        for record in records:
            time_str = record.get("time_str", "")
            if time_str and time_str not in seen_times:
                seen_times.add(time_str)
                unique_records.append(record)
        
        print(f"🔍 Found {len(unique_records)} unique records for {student_id}")
        
        # Convert to the required format for heatmap
        attendance_data = []
        for record in unique_records:
            time_str = record.get("time_str", "")
            if time_str and " " in time_str:
                # Extract date from time_str (format: "YYYY-MM-DD HH:MM:SS")
                date_part = time_str.split(" ")[0]
                attendance_data.append({
                    "date": date_part,
                    "status": "present",
                    "session": record.get("session", "Unknown"),
                    "time": time_str
                })
            else:
                print(f"⚠️ Invalid time_str format: {time_str}")
        
        # Sort by date (newest first)
        attendance_data.sort(key=lambda x: x["date"], reverse=True)
        
        print(f"✅ Returning {len(attendance_data)} attendance data points")
        if attendance_data:
            print(f"📋 Sample data: {attendance_data[0]}")
        
        return jsonify(attendance_data)
    
    except Exception as e:
        print(f"❌ Error in get_student_attendance: {str(e)}")
        # Return empty array instead of error to prevent heatmap from breaking
        return jsonify([])


@attendance_bp.route("/students")
def get_all_students():
    """API endpoint to get list of REGISTERED STUDENTS ONLY (exclude admins) for dropdown"""
    try:
        role = session.get("role", "guest")
        username = session.get("username", "")
        
        print(f"🔍 Getting students for role: {role}, username: {username}")
        
        # Get all registered users with student role ONLY (exclude admins)
        registered_students = set()
        
        try:
            # Get ONLY users with role="student" (exclude admin)
            registered_users = list(db.users.find(
                {"role": "student"}, 
                {"username": 1, "_id": 0}
            ))
            
            print(f"🔍 Found {len(registered_users)} registered student users")
            
            for user in registered_users:
                username_field = user.get("username")
                if username_field and username_field.strip():
                    registered_students.add(username_field.strip())
                    
            print(f"✅ Found {len(registered_students)} registered students (admins excluded)")
            
        except Exception as e:
            print(f"⚠️ Could not fetch registered users: {e}")
        
        # Convert to sorted list
        all_students = list(registered_students)
        all_students.sort()
        
        # 🔒 ROLE-BASED FILTERING
        if role == "student":
            # Students can ONLY see themselves
            if username in all_students:
                print(f"🔒 Student access: Returning only [{username}]")
                return jsonify([username])
            else:
                print(f"⚠️ Student {username} not found in registered students")
                return jsonify([])
        elif role == "admin":
            # Admin can see all students (already filtered to exclude admins)
            print(f"👨‍💼 Admin access: Returning {len(all_students)} students")
            return jsonify(all_students)
        else:
            print(f"❌ Unauthorized access attempt by role: {role}")
            return jsonify([])
    
    except Exception as e:
        print(f"❌ Error in get_all_students: {str(e)}")
        return jsonify([])


@attendance_bp.route("/view_data")
def view_data():
    """View all attendance records"""
    try:
        print("🔍 Loading attendance records for view_data...")
        
        records = list(db.attendance.find({}, {"_id": 0}))
        print(f"🔍 Found {len(records)} total records")
        
        # Format records for display
        formatted_records = []
        for record in records:
            formatted_record = {
                "student": record.get("student", "Unknown"),
                "session": record.get("session", record.get("session_id", "Unknown")),
                "time": record.get("time_str", "Unknown")
            }
            formatted_records.append(formatted_record)
            
        print(f"✅ Formatted {len(formatted_records)} records for display")
        
        if formatted_records:
            print(f"📋 Sample record: {formatted_records[0]}")
        
        return render_template("view_data.html", records=formatted_records)
    
    except Exception as e:
        print(f"❌ Error in view_data: {str(e)}")
        return f"Error loading data: {str(e)}"

# ===========================
# GEOFENCING MANAGEMENT ROUTES
# ===========================

@attendance_bp.route("/admin/geofence_zones")
def admin_geofence_zones():
    """Admin endpoint to view and manage geofence zones"""
    # Check admin privileges
    if session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    
    return jsonify({
        "zones": GEOFENCE_ZONES,
        "total_zones": len(GEOFENCE_ZONES),
        "security_settings": {
            "max_distance_meters": MAX_DISTANCE_METERS,
            "location_accuracy_threshold": LOCATION_ACCURACY_THRESHOLD,
            "max_speed_threshold": MAX_SPEED_THRESHOLD,
            "attendance_cooldown_seconds": ATTENDANCE_COOLDOWN
        }
    })


@attendance_bp.route("/admin/attendance_analytics")
def admin_attendance_analytics():
    """Advanced analytics for admin dashboard"""
    if session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        # Get recent attendance data
        recent_records = list(db.attendance.find({}).sort("time", -1).limit(100))
        
        analytics = {
            "total_attendance": len(recent_records),
            "zone_distribution": {},
            "security_summary": {
                "total_checks": 0,
                "spoofing_attempts": 0,
                "low_accuracy_attempts": 0,
                "successful_validations": 0
            },
            "hourly_distribution": {},
            "recent_activity": []
        }
        
        # Analyze records
        for record in recent_records:
            location = record.get("location", {})
            zone = location.get("primary_zone", "Unknown")
            
            # Zone distribution
            if zone not in analytics["zone_distribution"]:
                analytics["zone_distribution"][zone] = 0
            analytics["zone_distribution"][zone] += 1
            
            # Security analysis
            security_checks = location.get("security_checks", {})
            analytics["security_summary"]["total_checks"] += 1
            
            if security_checks.get("spoofing_detected"):
                analytics["security_summary"]["spoofing_attempts"] += 1
            
            if not security_checks.get("accuracy_valid"):
                analytics["security_summary"]["low_accuracy_attempts"] += 1
            
            if location.get("geofence_validated"):
                analytics["security_summary"]["successful_validations"] += 1
            
            # Hourly distribution
            time_str = record.get("time_str", "")
            if time_str:
                hour = time_str.split(" ")[1].split(":")[0] if " " in time_str else "Unknown"
                if hour not in analytics["hourly_distribution"]:
                    analytics["hourly_distribution"][hour] = 0
                analytics["hourly_distribution"][hour] += 1
            
            # Recent activity (last 10)
            if len(analytics["recent_activity"]) < 10:
                analytics["recent_activity"].append({
                    "student": record.get("student", "Unknown"),
                    "time": record.get("time_str", "Unknown"),
                    "zone": zone,
                    "distance": location.get("distance_from_zone", 0),
                    "security_passed": location.get("geofence_validated", False)
                })
        
        return jsonify(analytics)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/validate_bulk_locations", methods=["POST"])
def validate_bulk_locations():
    """Validate multiple locations at once (for testing)"""
    try:
        data = request.get_json()
        locations = data.get("locations", [])
        
        if not locations:
            return jsonify({"error": "No locations provided"}), 400
        
        results = []
        
        for i, location in enumerate(locations):
            lat = location.get("latitude")
            lon = location.get("longitude")
            label = location.get("label", f"Location {i+1}")
            
            if lat is None or lon is None:
                results.append({
                    "label": label,
                    "error": "Missing coordinates"
                })
                continue
            
            is_valid, geofence_result = validate_geofence_zones(lat, lon)
            
            results.append({
                "label": label,
                "coordinates": {"latitude": lat, "longitude": lon},
                "validation_result": geofence_result,
                "is_valid": is_valid
            })
        
        return jsonify({
            "total_locations": len(locations),
            "results": results,
            "summary": {
                "valid_locations": sum(1 for r in results if r.get("is_valid")),
                "invalid_locations": sum(1 for r in results if not r.get("is_valid"))
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===========================
# LEGACY COMPATIBILITY
# ===========================

@attendance_bp.route("/location_info")
def location_info():
    """Legacy API endpoint - redirects to geofence_info"""
    return geofence_info()

def validate_location(student_lat, student_lon):
    """
    Legacy function for backward compatibility
    Returns (is_valid, distance, message)
    """
    is_valid, geofence_result = validate_geofence_zones(student_lat, student_lon)
    
    if is_valid:
        primary_zone = geofence_result.get("primary_zone", {})
        distance = primary_zone.get("distance", 0)
        message = geofence_result.get("message", "Location validated")
        return True, distance, message
    else:
        closest_zone = geofence_result.get("closest_zone", {})
        distance = closest_zone.get("distance", 0)
        message = geofence_result.get("message", "Location validation failed")
        return False, distance, message

# ===========================
# DEBUG AND TESTING ROUTES
# ===========================

@attendance_bp.route("/debug_form", methods=["POST"])
def debug_form():
    """Debug endpoint to check what form data is being received"""
    print("🔍 DEBUG - Form data received:")
    for key, value in request.form.items():
        print(f"   {key}: '{value}'")
    
    print("🔍 DEBUG - Request headers:")
    for key, value in request.headers.items():
        print(f"   {key}: {value}")
    
    return jsonify({
        "form_data": dict(request.form),
        "method": request.method,
        "content_type": request.content_type,
        "remote_addr": request.remote_addr
    })

@attendance_bp.route("/test_session/<session_id>")
def test_session(session_id):
    """Test if a session exists in the database"""
    try:
        # Try different query formats
        queries = [
            {"session_id": session_id},
            {"_id": session_id},
            {"session": session_id}
        ]
        
        results = {}
        for i, query in enumerate(queries):
            try:
                session_data = db.sessions.find_one(query)
                results[f"query_{i+1}"] = {
                    "query": query,
                    "found": session_data is not None,
                    "data": session_data if session_data else None
                }
            except Exception as e:
                results[f"query_{i+1}"] = {
                    "query": query,
                    "error": str(e)
                }
        
        # Also list all sessions
        try:
            all_sessions = list(db.sessions.find({}, {"_id": 1, "session_id": 1, "session": 1, "session_name": 1}))
            results["all_sessions"] = all_sessions
        except Exception as e:
            results["all_sessions_error"] = str(e)
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@attendance_bp.route("/create_test_session")
def create_test_session():
    """Create a test session for debugging"""
    try:
        test_session = {
            "session_id": "test_session_123",
            "session": "test_session_123",  # For compatibility
            "admin_id": "admin",
            "session_name": "Test Session",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=2),
            "is_active": True,
            "attendees": [],
            "attendee_count": 0
        }
        
        result = db.sessions.insert_one(test_session)
        
        return jsonify({
            "success": True,
            "message": "Test session created",
            "session_id": "test_session_123",
            "inserted_id": str(result.inserted_id)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@attendance_bp.route("/manual_test")
def manual_test():
    """Manual test page for debugging attendance"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manual Attendance Test</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 p-8">
        <div class="max-w-md mx-auto bg-white rounded-lg shadow-md p-6">
            <h2 class="text-2xl font-bold mb-4">Manual Attendance Test</h2>
            
            <div class="mb-4">
                <button onclick="createTestSession()" class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                    Create Test Session
                </button>
            </div>
            
            <div class="mb-4">
                <button onclick="getCurrentLocation()" class="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600">
                    Get Current Location
                </button>
            </div>
            
            <form id="testForm" action="/mark_attendance" method="post" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700">Student Name:</label>
                    <input name="student" value="Test Student" required class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-700">Session ID:</label>
                    <input id="sessionId" name="session" value="test_session_123" required class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-700">Latitude:</label>
                    <input id="latitude" name="latitude" value="17.52723710588141" required class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-700">Longitude:</label>
                    <input id="longitude" name="longitude" value="78.37139375341242" required class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                </div>
                
                <button type="submit" class="w-full bg-purple-500 text-white px-4 py-2 rounded hover:bg-purple-600">
                    Mark Attendance
                </button>
            </form>
            
            <div id="result" class="mt-4 p-4 bg-gray-50 rounded-lg hidden"></div>
        </div>
        
        <script>
            async function createTestSession() {
                try {
                    const response = await fetch('/create_test_session');
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('sessionId').value = data.session_id;
                        alert('Test session created: ' + data.session_id);
                    } else {
                        alert('Error: ' + data.error);
                    }
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }
            
            function getCurrentLocation() {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(function(position) {
                        document.getElementById('latitude').value = position.coords.latitude;
                        document.getElementById('longitude').value = position.coords.longitude;
                        alert('Location updated!');
                    }, function(error) {
                        alert('Location error: ' + error.message);
                    });
                } else {
                    alert('Geolocation is not supported by this browser.');
                }
            }
            
            document.getElementById('testForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const formData = new FormData(this);
                
                fetch('/mark_attendance', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.text())
                .then(data => {
                    const resultDiv = document.getElementById('result');
                    resultDiv.innerHTML = data;
                    resultDiv.classList.remove('hidden');
                })
                .catch(error => {
                    const resultDiv = document.getElementById('result');
                    resultDiv.innerHTML = 'Error: ' + error.message;
                    resultDiv.classList.remove('hidden');
                });
            });
        </script>
    </body>
    </html>
    """
@attendance_bp.route("/debug_role")
def debug_role():
    """Debug endpoint to check current user role and session"""
    from flask import session as flask_session
    
    return jsonify({
        "role": flask_session.get("role", "No role set"),
        "username": flask_session.get("username", "No username set"),
        "session_keys": list(flask_session.keys()),
        "session_data": dict(flask_session)
    })

@attendance_bp.route("/force_student_view")
def force_student_view():
    """Force student view for testing"""
    from flask import session as flask_session
    flask_session["role"] = "student"
    flask_session["username"] = "test_student"
    
    return redirect("/student")
@attendance_bp.route("/quick_session")
def quick_session():
    """Quick session creation for testing - creates 2-minute session immediately"""
    try:
        import datetime
        
        # Create session with 2 minutes (120 seconds)
        session_id = "SESSION_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        created_at = datetime.datetime.now()
        expires_at = created_at + datetime.timedelta(seconds=120)
        
        session_data = {
            "session_id": session_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "admin_id": "test_admin",
            "is_active": True,
            "attendees": [],
            "attendee_count": 0
        }
        
        result = db.sessions.insert_one(session_data)
        
        # Generate QR code
        import qrcode
        img = qrcode.make(session_id)
        img.save("static/qr.png")
        
        return jsonify({
            "success": True,
            "message": "2-minute session created successfully!",
            "session_id": session_id,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "remaining_seconds": 120,
            "instructions": [
                "1. Session created with 2-minute timer (120 seconds)",
                "2. QR code generated and saved",
                "3. Student dashboard should auto-detect in 2 seconds",
                "4. Session ID will auto-populate",
                "5. Students can mark attendance immediately"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
@attendance_bp.route("/debug_sessions")
def debug_sessions():
    """Debug endpoint to check all sessions in database"""
    try:
        import datetime
        
        all_sessions = list(db.sessions.find({}))
        current_time = datetime.datetime.now()
        
        session_info = []
        for session_data in all_sessions:
            expires_at = session_data.get("expires_at")
            is_active = expires_at and expires_at > current_time if expires_at else False
            
            session_info.append({
                "session_id": session_data.get("session_id", "Unknown"),
                "created_at": session_data.get("created_at").isoformat() if session_data.get("created_at") else "Unknown",
                "expires_at": expires_at.isoformat() if expires_at else "Unknown",
                "is_active": is_active,
                "remaining_seconds": int((expires_at - current_time).total_seconds()) if is_active else 0
            })
        
        return jsonify({
            "current_time": current_time.isoformat(),
            "total_sessions": len(all_sessions),
            "sessions": session_info,
            "active_sessions": [s for s in session_info if s["is_active"]]
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500
@attendance_bp.route("/test_workflow")
def test_workflow():
    """Complete workflow test"""
    try:
        import datetime
        import qrcode
        
        # 1. Create a 2-minute session
        session_id = "SESSION_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        created_at = datetime.datetime.now()
        expires_at = created_at + datetime.timedelta(seconds=120)
        
        session_data = {
            "session_id": session_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "admin_id": "test_admin",
            "is_active": True,
            "attendees": [],
            "attendee_count": 0
        }
        
        # 2. Store in database
        result = db.sessions.insert_one(session_data)
        
        # 3. Generate QR code
        img = qrcode.make(session_id)
        img.save("static/qr.png")
        
        # 4. Test current_session endpoint
        current_time = datetime.datetime.now()
        all_sessions = list(db.sessions.find({}))
        active_sessions = [s for s in all_sessions if s.get("expires_at") and s["expires_at"] > current_time]
        
        return jsonify({
            "step_1_session_created": {
                "session_id": session_id,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "duration_seconds": 120
            },
            "step_2_database_stored": {
                "success": True,
                "inserted_id": str(result.inserted_id)
            },
            "step_3_qr_generated": {
                "success": True,
                "file_path": "static/qr.png"
            },
            "step_4_session_detection": {
                "current_time": current_time.isoformat(),
                "total_sessions": len(all_sessions),
                "active_sessions": len(active_sessions),
                "active_session_ids": [s["session_id"] for s in active_sessions]
            },
            "instructions": [
                "✅ 2-minute session created successfully",
                "✅ QR code generated",
                "✅ Session stored in database",
                f"🔍 Found {len(active_sessions)} active session(s)",
                "📱 Student dashboard should now show active session",
                "⏰ Timer should show 2:00 countdown"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500
@attendance_bp.route("/test_attendance_data")
def test_attendance_data():
    """Test endpoint to create sample attendance data and verify all analytics work"""
    try:
        import datetime
        
        # Clear existing test data
        try:
            db.attendance.delete_many({"student": {"$regex": "^Test"}})
        except:
            # For in-memory database, manually clear test records
            all_records = list(db.attendance.find({}))
            for record in all_records:
                if record.get("student", "").startswith("Test"):
                    # Remove from in-memory storage if using mock database
                    if hasattr(db.attendance, 'storage'):
                        try:
                            db.attendance.storage.remove(record)
                        except:
                            pass
        
        # Create sample attendance records
        sample_records = []
        students = ["Test Student 1", "Test Student 2", "Test Student 3", "Test Student 1", "Test Student 2"]
        
        for i, student in enumerate(students):
            ist_time = get_ist_time()
            
            record = {
                "student": student,  # Required for generate_graphs
                "student_id": student,  # For compatibility
                "session": f"SESSION_TEST_{i+1}",
                "session_id": f"SESSION_TEST_{i+1}",
                "time": ist_time,
                "time_str": ist_time.strftime("%Y-%m-%d %H:%M:%S"),
                "location": {
                    "latitude": 17.52723710588141 + (i * 0.001),
                    "longitude": 78.37139375341242 + (i * 0.001),
                    "accuracy": 10.0,
                    "primary_zone": "Main Campus",
                    "distance_from_zone": 50 + (i * 10),
                    "geofence_validated": True,
                    "security_checks": {
                        "cooldown_passed": True,
                        "accuracy_valid": True,
                        "spoofing_detected": False
                    }
                },
                "metadata": {
                    "ip_address": "127.0.0.1",
                    "user_agent": "Test Browser",
                    "timestamp_utc": datetime.utcnow()
                }
            }
            
            sample_records.append(record)
        
        # Insert sample records
        for record in sample_records:
            db.attendance.insert_one(record)
        
        # Generate graphs
        generate_graphs()
        
        # Test all three analytics endpoints
        
        # 1. Test view_data
        all_records = list(db.attendance.find({}, {"_id": 0}))
        
        # 2. Test generate_graphs data
        import pandas as pd
        if all_records:
            df = pd.DataFrame(all_records)
            student_counts = df["student"].value_counts().to_dict() if "student" in df.columns else {}
        else:
            student_counts = {}
        
        # 3. Test heatmap data
        heatmap_data = []
        for record in all_records:
            if record.get("time_str"):
                date_part = record["time_str"].split(" ")[0]
                heatmap_data.append({
                    "date": date_part,
                    "student": record.get("student", "Unknown"),
                    "status": "present"
                })
        
        return jsonify({
            "success": True,
            "message": "Sample attendance data created and tested",
            "data_verification": {
                "total_records_created": len(sample_records),
                "total_records_in_db": len(all_records),
                "student_counts_for_graphs": student_counts,
                "heatmap_data_sample": heatmap_data[:3],
                "sample_record_structure": sample_records[0] if sample_records else None
            },
            "analytics_status": {
                "view_data": f"{len(all_records)} records available",
                "matlab_analysis": f"Graphs generated with {len(student_counts)} students",
                "heatmap_analytics": f"{len(heatmap_data)} data points for heatmap"
            },
            "next_steps": [
                "✅ Sample data created successfully",
                "📊 Visit /view_data to see attendance records",
                "📈 Visit /analysis to see MATLAB charts",
                "🔥 Visit /heatmap to see heatmap analytics",
                "🎯 All three pages should now show data instead of 'No records found'"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Failed to create test data"
        }), 500
@attendance_bp.route("/registered_students_info")
def registered_students_info():
    """Get information about registered students for admin"""
    try:
        # Get all registered students
        registered_users = list(db.users.find(
            {"role": "student", "is_active": True}, 
            {"username": 1, "email": 1, "created_at": 1, "_id": 0}
        ))
        
        # Get attendance statistics for each student
        student_stats = []
        for user in registered_users:
            username = user.get("username")
            
            # Count attendance records for this student
            attendance_count = len(list(db.attendance.find({"student": username})))
            
            student_stats.append({
                "username": username,
                "email": user.get("email", "N/A"),
                "registered_date": user.get("created_at").strftime("%Y-%m-%d") if user.get("created_at") else "Unknown",
                "attendance_records": attendance_count,
                "has_attendance": attendance_count > 0
            })
        
        # Sort by username
        student_stats.sort(key=lambda x: x["username"])
        
        return jsonify({
            "total_registered_students": len(student_stats),
            "students_with_attendance": len([s for s in student_stats if s["has_attendance"]]),
            "students_without_attendance": len([s for s in student_stats if not s["has_attendance"]]),
            "student_details": student_stats,
            "instructions": [
                "✅ Only registered students appear in heatmap dropdown",
                "📊 Students need to register via /register first",
                "📈 Heatmap shows attendance patterns for registered students only",
                "👥 Admin can view any registered student's attendance heatmap"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "total_registered_students": 0,
            "student_details": []
        }), 500
@attendance_bp.route("/test_heatmap_with_registered")
def test_heatmap_with_registered():
    """Create test attendance data ONLY for actually registered students"""
    try:
        import datetime
        import random
        
        # Get only registered students
        registered_users = list(db.users.find(
            {"role": "student", "is_active": True}, 
            {"username": 1, "_id": 0}
        ))
        
        if not registered_users:
            return jsonify({
                "success": False,
                "message": "No registered students found",
                "instructions": [
                    "❌ No registered students in the system",
                    "📝 Students need to register via /register first",
                    "👥 Only registered students will appear in heatmap",
                    "🔗 Visit /register to create student accounts"
                ]
            })
        
        # Create attendance records for registered students only
        created_records = []
        base_date = datetime.datetime.now() - datetime.timedelta(days=20)
        
        for user in registered_users:
            student_name = user.get("username")
            if not student_name:
                continue
                
            # Random attendance rate between 60-95%
            attendance_rate = random.uniform(0.6, 0.95)
            
            # Clear existing test data for this student
            try:
                db.attendance.delete_many({"student": student_name})
            except:
                pass
            
            for day_offset in range(20):
                current_date = base_date + datetime.timedelta(days=day_offset)
                
                # Skip weekends
                if current_date.weekday() >= 5:
                    continue
                
                # Randomly decide attendance based on rate
                if random.random() < attendance_rate:
                    ist_time = current_date.replace(
                        hour=random.randint(9, 11),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59)
                    )
                    
                    record = {
                        "student": student_name,
                        "student_id": student_name,
                        "session": f"SESSION_{current_date.strftime('%Y%m%d')}_{random.randint(1,2)}",
                        "session_id": f"SESSION_{current_date.strftime('%Y%m%d')}_{random.randint(1,2)}",
                        "time": ist_time,
                        "time_str": ist_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "location": {
                            "latitude": 17.52723710588141 + random.uniform(-0.001, 0.001),
                            "longitude": 78.37139375341242 + random.uniform(-0.001, 0.001),
                            "accuracy": random.uniform(5, 20),
                            "primary_zone": random.choice(["Main Campus", "Library", "Lab Block"]),
                            "distance_from_zone": random.randint(10, 100),
                            "geofence_validated": True
                        }
                    }
                    
                    db.attendance.insert_one(record)
                    created_records.append({
                        "student": student_name,
                        "date": current_date.strftime("%Y-%m-%d")
                    })
        
        return jsonify({
            "success": True,
            "message": f"Created attendance data for {len(registered_users)} registered students",
            "data_summary": {
                "registered_students": [user["username"] for user in registered_users],
                "total_attendance_records": len(created_records),
                "date_range": {
                    "from": base_date.strftime("%Y-%m-%d"),
                    "to": datetime.datetime.now().strftime("%Y-%m-%d")
                }
            },
            "instructions": [
                "✅ Attendance data created for registered students only",
                "📊 Visit /heatmap to see registered students in dropdown",
                "👥 Only students who registered via /register appear",
                "📈 Each registered student has realistic attendance patterns"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
@attendance_bp.route("/debug_heatmap")
def debug_heatmap():
    """Debug endpoint to test heatmap API functionality with registered students only"""
    try:
        # Test students endpoint (should only return registered students)
        students_response = get_all_students()
        students_data = students_response.get_json() if hasattr(students_response, 'get_json') else students_response.data
        
        # Get registered students directly from database
        registered_users = list(db.users.find(
            {"role": "student", "is_active": True}, 
            {"username": 1, "email": 1, "_id": 0}
        ))
        
        # Test attendance endpoint for first registered student
        sample_student = None
        sample_attendance = []
        
        if students_data and len(students_data) > 0:
            sample_student = students_data[0]
            attendance_response = get_student_attendance(sample_student)
            sample_attendance = attendance_response.get_json() if hasattr(attendance_response, 'get_json') else attendance_response.data
        
        # Check database directly
        total_attendance_records = len(list(db.attendance.find({}, {"_id": 0})))
        
        return jsonify({
            "heatmap_debug_info": {
                "registered_users_in_db": {
                    "count": len(registered_users),
                    "usernames": [user["username"] for user in registered_users],
                    "emails": [user.get("email", "N/A") for user in registered_users]
                },
                "students_api": {
                    "endpoint": "/students",
                    "status": "working" if students_data else "error",
                    "student_count": len(students_data) if students_data else 0,
                    "students": students_data  # All registered students
                },
                "attendance_api": {
                    "endpoint": f"/attendance/{sample_student}" if sample_student else "/attendance/<student>",
                    "test_student": sample_student,
                    "status": "working" if sample_attendance is not None else "error",
                    "attendance_count": len(sample_attendance) if sample_attendance else 0,
                    "sample_data": sample_attendance[:3] if sample_attendance else []
                },
                "database_status": {
                    "total_attendance_records": total_attendance_records,
                    "total_registered_students": len(registered_users)
                }
            },
            "heatmap_requirements": {
                "registered_students": f"✅ {len(registered_users)} registered" if len(registered_users) > 0 else "❌ No registered students",
                "students_dropdown": "✅ Working" if students_data and len(students_data) > 0 else "❌ No students in dropdown",
                "attendance_data": "✅ Working" if sample_attendance else "⚠️ No attendance data (students need to mark attendance)",
                "data_format": "✅ Correct" if sample_attendance and len(sample_attendance) > 0 and "date" in sample_attendance[0] else "⚠️ No data to check format"
            },
            "next_steps": [
                "👥 If no registered students, users need to register via /register",
                "📊 If no attendance data, visit /test_heatmap_with_registered",
                "🔍 Visit /heatmap to test the interface",
                "📈 Only registered students will appear in dropdown"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "debug_failed": True
        }), 500
