"""
Database Configuration for Smart Attendance System
MongoDB connection and collection management
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from typing import Optional, Dict, Any, List

class Database:
    def __init__(self):
        """Initialize MongoDB connection"""
        self.client = None
        self.db = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Establish connection to MongoDB Atlas"""
        try:
            # MongoDB Atlas connection string
            # Replace <username>, <password>, and cluster URL with your actual credentials
            mongo_uri = os.getenv(
                'MONGODB_URI', 
                'mongodb+srv://23wh1a04c0:sskksmart@cluster2.fojnwul.mongodb.net/?retryWrites=true&w=majority&appName=Cluster2'
            )
            
            # Initialize MongoClient with Atlas-optimized settings
            self.client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            
            # Database name
            db_name = os.getenv('DB_NAME', 'attendance_system')
            self.db = self.client[db_name]
            
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            print("✅ Connected to MongoDB Atlas successfully")
            print(f"✅ Using database: {db_name}")
            
        except Exception as e:
            print(f"⚠️ MongoDB Atlas connection failed: {e}")
            print("📝 Running in offline mode - using in-memory storage")
            self.connected = False
            self._setup_fallback_storage()
    
    def _setup_fallback_storage(self):
        """Setup in-memory storage when MongoDB is not available"""
        self._memory_storage = {
            'users': [],
            'attendance': [],
            'sessions': [],
            'qr_codes': [],
            'password_resets': []
        }
        
        # Create mock collections
        class MockCollection:
            def __init__(self, storage_list):
                self.storage = storage_list
            
            def insert_one(self, document):
                import uuid
                document['_id'] = str(uuid.uuid4())
                self.storage.append(document)
                class MockResult:
                    def __init__(self, doc_id):
                        self.inserted_id = doc_id
                return MockResult(document['_id'])
            
            def find_one(self, query=None, *args, **kwargs):
                if not query:
                    return self.storage[0] if self.storage else None
                
                for doc in self.storage:
                    match = True
                    for key, value in query.items():
                        if key not in doc or doc[key] != value:
                            match = False
                            break
                    if match:
                        return doc
                return None
            
            def find(self, query=None, *args, **kwargs):
                if not query:
                    return self.storage.copy()
                
                results = []
                for doc in self.storage:
                    match = True
                    for key, value in query.items():
                        if key not in doc:
                            match = False
                            break
                        
                        # Handle MongoDB-style operators
                        if isinstance(value, dict):
                            doc_value = doc[key]
                            for operator, op_value in value.items():
                                if operator == "$gt" and doc_value <= op_value:
                                    match = False
                                    break
                                elif operator == "$lt" and doc_value >= op_value:
                                    match = False
                                    break
                                elif operator == "$gte" and doc_value < op_value:
                                    match = False
                                    break
                                elif operator == "$lte" and doc_value > op_value:
                                    match = False
                                    break
                        else:
                            if doc[key] != value:
                                match = False
                                break
                    
                    if match:
                        results.append(doc)
                
                # Handle sorting
                sort_param = kwargs.get('sort')
                if sort_param:
                    for field, direction in sort_param:
                        reverse = direction == -1
                        results.sort(key=lambda x: x.get(field, 0), reverse=reverse)
                
                return results
            
            def update_one(self, query, update, *args, **kwargs):
                doc = self.find_one(query)
                if doc and '$set' in update:
                    doc.update(update['$set'])
                    class MockResult:
                        modified_count = 1 if doc else 0
                    return MockResult()
                
                class MockResult:
                    modified_count = 0
                return MockResult()
            
            def count_documents(self, query=None):
                if not query:
                    return len(self.storage)
                return len(self.find(query))
            
            def distinct(self, field):
                values = set()
                for doc in self.storage:
                    if field in doc:
                        values.add(doc[field])
                return list(values)
            
            def delete_many(self, query):
                to_remove = []
                for i, doc in enumerate(self.storage):
                    match = True
                    for key, value in query.items():
                        if key not in doc or doc[key] != value:
                            match = False
                            break
                    if match:
                        to_remove.append(i)
                
                for i in reversed(to_remove):
                    del self.storage[i]
                
                class MockResult:
                    def __init__(self, count):
                        self.deleted_count = count
                return MockResult(len(to_remove))
            
            def create_index(self, *args, **kwargs):
                pass  # No-op for in-memory storage
        # Create mock database
        class MockDB:
            def __init__(self, storage):
                self.users = MockCollection(storage['users'])
                self.attendance = MockCollection(storage['attendance'])
                self.sessions = MockCollection(storage['sessions'])
                self.qr_codes = MockCollection(storage['qr_codes'])
                self.password_resets = MockCollection(storage['password_resets'])
        
        self.db = MockDB(self._memory_storage)
        self.db = MockDB(self._memory_storage)
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client and self.connected:
            self.client.close()
            print("✅ MongoDB connection closed")
        elif not self.connected:
            print("✅ In-memory storage cleared")

    # Collections
    @property
    def users(self):
        """Users collection for authentication"""
        return self.db.users
    
    @property
    def attendance(self):
        """Attendance records collection"""
        return self.db.attendance
    
    @property
    def sessions(self):
        """Active sessions collection"""
        return self.db.sessions
    
    @property
    def qr_codes(self):
        """QR codes collection"""
        return self.db.qr_codes
    
    @property
    def password_resets(self):
        """Password reset tokens collection"""
        return self.db.password_resets

    # User Management Methods
    def create_user(self, username: str, email: str, password_hash: str, 
                   role: str = 'student', **kwargs) -> str:
        """Create a new user"""
        user_data = {
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'role': role,
            'created_at': datetime.utcnow(),
            'is_active': True,
            **kwargs
        }
        
        result = self.users.insert_one(user_data)
        return str(result.inserted_id)
    
    def find_user(self, **query) -> Optional[Dict[str, Any]]:
        """Find a user by query parameters"""
        return self.users.find_one(query)
    
    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Update user information"""
        from bson import ObjectId
        result = self.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {**update_data, 'updated_at': datetime.utcnow()}}
        )
        return result.modified_count > 0

    # Attendance Management Methods
    def record_attendance(self, student_id: str, session_id: str, 
                         latitude: float, longitude: float, **kwargs) -> str:
        """Record student attendance with enhanced geolocation data"""
        attendance_data = {
            'student_id': student_id,
            'student': student_id,  # For backward compatibility
            'session_id': session_id,
            'session': session_id,  # For backward compatibility
            'latitude': latitude,
            'longitude': longitude,
            'timestamp': datetime.utcnow(),
            'time': datetime.utcnow(),  # For backward compatibility
            'status': 'present',
            'location': {
                'latitude': latitude,
                'longitude': longitude,
                'accuracy': kwargs.get('accuracy'),
                'primary_zone': kwargs.get('primary_zone', 'Unknown'),
                'distance_from_zone': kwargs.get('distance_from_zone', 0),
                'geofence_validated': kwargs.get('geofence_validated', False),
                'security_checks': kwargs.get('security_checks', {})
            },
            'metadata': {
                'ip_address': kwargs.get('ip_address'),
                'user_agent': kwargs.get('user_agent'),
                'timestamp_utc': datetime.utcnow()
            },
            **kwargs
        }
        
        result = self.attendance.insert_one(attendance_data)
        return str(result.inserted_id)
    
    def get_attendance_records(self, **filters) -> List[Dict[str, Any]]:
        """Get attendance records with optional filters"""
        return list(self.attendance.find(filters))
    
    def get_student_attendance(self, student_id: str) -> List[Dict[str, Any]]:
        """Get all attendance records for a specific student"""
        return list(self.attendance.find({'student_id': student_id}))

    # Session Management Methods
    def create_session(self, admin_id: str, session_name: str, 
                      location: Dict[str, float], **kwargs) -> str:
        """Create a new attendance session with enhanced tracking"""
        session_data = {
            'admin_id': admin_id,
            'session_name': session_name,
            'session_id': kwargs.get('session_id', f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"),
            'location': location,  # {'latitude': float, 'longitude': float}
            'created_at': datetime.utcnow(),
            'expires_at': kwargs.get('expires_at', datetime.utcnow() + timedelta(hours=2)),
            'is_active': True,
            'attendees': [],
            'attendee_count': 0,
            'geofence_settings': {
                'enabled': kwargs.get('geofence_enabled', True),
                'zones': kwargs.get('allowed_zones', ['main_campus']),
                'strict_mode': kwargs.get('strict_mode', False)
            },
            **kwargs
        }
        
        result = self.sessions.insert_one(session_data)
        return str(result.inserted_id)
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        return list(self.sessions.find({'is_active': True}))
    
    def end_session(self, session_id: str) -> bool:
        """End an active session"""
        from bson import ObjectId
        result = self.sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$set': {'is_active': False, 'ended_at': datetime.utcnow()}}
        )
        return result.modified_count > 0

    # QR Code Management Methods
    def save_qr_code(self, session_id: str, qr_data: str, **kwargs) -> str:
        """Save QR code information"""
        qr_record = {
            'session_id': session_id,
            'qr_data': qr_data,
            'created_at': datetime.utcnow(),
            'is_active': True,
            **kwargs
        }
        
        result = self.qr_codes.insert_one(qr_record)
        return str(result.inserted_id)
    
    def get_qr_code(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get QR code for a session"""
        return self.qr_codes.find_one({'session_id': session_id, 'is_active': True})

    # Analytics Methods
    def get_attendance_stats(self) -> Dict[str, Any]:
        """Get attendance statistics"""
        total_records = self.attendance.count_documents({})
        total_students = len(self.attendance.distinct('student_id'))
        total_sessions = self.sessions.count_documents({})
        
        return {
            'total_attendance_records': total_records,
            'total_students': total_students,
            'total_sessions': total_sessions,
            'active_sessions': self.sessions.count_documents({'is_active': True})
        }
    
    def get_daily_attendance(self, date: datetime) -> List[Dict[str, Any]]:
        """Get attendance records for a specific date"""
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return list(self.attendance.find({
            'timestamp': {'$gte': start_date, '$lte': end_date}
        }))
    def create_indexes(self):
        """Create database indexes for better performance"""
        if not self.connected:
            print("⚠️ Skipping index creation - using in-memory storage")
            return
            
        try:
            # User indexes
            self.users.create_index('username', unique=True)
            self.users.create_index('email', unique=True)
            
            # Attendance indexes
            self.attendance.create_index('student_id')
            self.attendance.create_index('session_id')
            self.attendance.create_index('timestamp')
            
            # Session indexes
            self.sessions.create_index('admin_id')
            self.sessions.create_index('is_active')
            
            # Password reset indexes
            self.password_resets.create_index('email')
            self.password_resets.create_index('token_hash')
            self.password_resets.create_index('expires_at')
            
            print("✅ Database indexes created successfully")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old inactive data"""
        if not self.connected:
            print("⚠️ Skipping cleanup - using in-memory storage")
            return
            
        try:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Remove old inactive sessions
            result = self.sessions.delete_many({
                'is_active': False,
                'ended_at': {'$lt': cutoff_date}
            })
            
            print(f"✅ Cleaned up {result.deleted_count} old sessions")
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

# Global database instance
db = Database()

# Initialize indexes on startup
try:
    db.create_indexes()
except Exception as e:
    print(f"⚠️ Index creation warning: {e}")

# Add some sample data if running in offline mode
if not db.connected:
    print("📝 Adding sample data for offline mode...")
    
    # Add sample session
    sample_session = {
        'session_id': 'sample_session_001',
        'admin_id': 'admin',
        'session_name': 'Sample Class',
        'created_at': datetime.utcnow(),
        'expires_at': datetime.utcnow() + timedelta(hours=2),
        'is_active': True,
        'attendees': [],
        'attendee_count': 0
    }
    db.sessions.insert_one(sample_session)
    
    print("✅ Sample data added for testing")
