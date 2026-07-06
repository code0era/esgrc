import sys
from pymongo import MongoClient

uri = "mongodb+srv://ashubhamyadav61_db_user:QMT5s9Imc35SmyvC@cluster0.y9a9czi.mongodb.net/?appName=Cluster0"
try:
    print("Connecting...")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("Connected successfully")
except Exception as e:
    print(f"Error: {e}")
