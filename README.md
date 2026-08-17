🎓 Smart Attendance System
A Flask-based intelligent attendance management system with advanced geofencing, QR code scanning, and real-time analytics.

Python Flask MongoDB License

🌟 Features
🔒 Security & Authentication
Role-Based Access Control (RBAC) - Separate student and admin roles
Session Management - Prevents multiple simultaneous logins
Secure Password Reset - Email-based token authentication with SHA-256 hashing
Anti-Spoofing Protection - Prevents attendance fraud
📍 Advanced Geofencing
Multi-Zone Validation - Main Campus, Library, Hostel zones with priority-based selection
GPS Distance Calculation - Haversine formula for accurate distance measurement
Location Security Checks:
GPS accuracy validation (<100m threshold)
Speed-based spoofing detection (<50 km/h)
5-minute cooldown between attendance marks
Real Coordinates - BVRIT Hyderabad College (17.527°N, 78.371°E)
📱 QR Code System
Time-Limited Sessions - 2-minute QR code expiry
Real-Time Updates - Auto-refresh every 2 seconds
Countdown Timers - Visual feedback for session expiration
Session Validation - Backend expiration checks
📊 Analytics & Reports
Interactive Heatmaps - 12-week attendance visualization
Role-Based Analytics:
Students: View only their own data
Admins: View all students (admins excluded from analytics)
Automated Charts - Bar charts and pie charts using matplotlib
CSV Export - Download attendance records
Attendance Rate Calculation - Real-time percentage tracking
🌐 Deployment
MongoDB Atlas Integration - Cloud-based data persistence
ngrok Support - Public URL for external access
Offline Mode - In-memory fallback for development
🚀 Quick Start
Prerequisites
Python 3.8 or higher
MongoDB Atlas account (or local MongoDB)
Gmail account for email features (optional)
Installation
Clone the repository
git clone https://github.com/yourusername/smart-attendance-system.git
cd smart-attendance-system
Install dependencies
pip install -r requirements.txt
Configure MongoDB Atlas

Create a MongoDB Atlas account at https://www.mongodb.com/cloud/atlas
Create a new cluster
Get your connection string
Update db.py with your connection string:
MONGO_URI = "your_mongodb_atlas_connection_string"
Configure Email (Optional)

Update app.py with your Gmail credentials:
app.config['MAIL_USERNAME'] = "your-email@gmail.com"
app.config['MAIL_PASSWORD'] = "your-app-password"
Configure ngrok (Optional)

Sign up at https://ngrok.com
Get your auth token
Update app.py:
ngrok.set_auth_token("your_ngrok_token")
Run the application

python app.py
Access the application
Local: http://127.0.0.1:5000
Public: Your ngrok URL (displayed in console)
📖 Usage
Admin Access
Username: admin123
Password: admin@123
Admin Capabilities:

Generate QR codes for attendance sessions
View all student analytics
Export attendance data to CSV
View security reports
Manage geofence zones
Student Access
Register at /register
Login with your credentials
Scan QR code or enter session ID
Enable location services
Mark attendance (validates location automatically)
View your own attendance heatmap
🏗️ Project Structure
smart-attendance-system/
├── app.py                          # Main Flask application
├── auth.py                         # Authentication & user management
├── attendance.py                   # Attendance & geofencing logic
├── qr.py                          # QR code generation & session management
├── db.py                          # Database configuration & models
├── requirements.txt               # Python dependencies
├── templates/                     # HTML templates
│   ├── login.html
│   ├── register.html
│   ├── student.html
│   ├── admin.html
│   ├── heatmap.html
│   ├── analysis.html
│   └── ...
├── static/                        # Static files
│   ├── qr.png                    # Generated QR codes
│   ├── bar_chart.png             # Attendance bar chart
│   └── pie_chart.png             # Attendance pie chart
└── README.md
🔧 Configuration
Geofence Zones
Edit attendance.py to customize zones:

GEOFENCE_ZONES = {
    "main_campus": {
        "name": "Main Campus",
        "latitude": 17.52723710588141,
        "longitude": 78.37139375341242,
        "radius": 500,  # meters
        "priority": 1
    },
    # Add more zones...
}
Security Settings
LOCATION_ACCURACY_THRESHOLD = 100  # meters
MAX_SPEED_THRESHOLD = 50           # km/h
ATTENDANCE_COOLDOWN = 300          # seconds (5 minutes)
🛡️ Security Features
Implemented Security Measures
Session-Based Authentication - Prevents attendance spoofing
Location Validation - Multi-layer geofencing
Role-Based Access Control - Students can only view their own data
Admin Attendance Prevention - Admins cannot mark attendance
SQL Injection Prevention - Parameterized queries
XSS Protection - Input sanitization
CSRF Protection - Form tokens
Data Stored for Audit Trail
Student name and session ID
GPS coordinates and accuracy
Geofence zone and distance
Security check results
IP address and user agent
Timestamp (IST timezone)
📊 API Endpoints
Authentication
GET/POST / - Login page
GET/POST /register - User registration
GET /logout - Logout
GET/POST /forgot-password - Password reset request
GET/POST /reset-password/<token> - Password reset
Attendance
POST /mark_attendance - Mark attendance
GET /students - Get all students (role-based)
GET /attendance/<student_id> - Get student attendance data
QR & Sessions
GET/POST /create_qr - Generate QR code (admin only)
GET /current_session - Get active session
GET /refresh_qr - Create new session
Analytics
GET /heatmap - Attendance heatmap page
GET /analysis - Analytics with charts
GET /view_data - View all attendance records
GET /export_csv - Export to CSV
Geofencing
POST /test_location - Test geofencing validation
GET /geofence_info - Get geofence configuration
GET /security_report/<student_id> - Security analysis
🧪 Testing
Test Endpoints
/test_csv_export - Create sample attendance data
/test_location - Test geofencing
/manual_test - Manual attendance testing page
/debug_heatmap - Debug heatmap API
Test Workflow
Create test session: /quick_session
View sessions: /debug_sessions
Test complete flow: /test_workflow
🤝 Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

Fork the repository
Create your feature branch (git checkout -b feature/AmazingFeature)
Commit your changes (git commit -m 'Add some AmazingFeature')
Push to the branch (git push origin feature/AmazingFeature)
Open a Pull Request
📝 License
This project is licensed under the MIT License - see the LICENSE file for details.

👨‍💻 Author
Your Name

GitHub: @yourusername
Email: your.email@example.com
🙏 Acknowledgments
BVRIT Hyderabad College of Engineering for Women
Flask framework and community
MongoDB Atlas for cloud database
ngrok for public tunneling
📞 Support
For support, email your.email@example.com or open an issue in the GitHub repository.

🔮 Future Enhancements
 Mobile app (React Native)
 Face recognition integration
 Push notifications for students
 Automated email reports to faculty
 Multi-tenant support for multiple institutions
 Advanced analytics with machine learning
 Bluetooth beacon support
 Offline attendance with sync
📸 Screenshots
Student Dashboard
Student Dashboard

Admin Dashboard
Admin Dashboard

Heatmap Analytics
Heatmap

⭐ Star this repo if you find it helpful!

Made with ❤️ using Flask and Python
