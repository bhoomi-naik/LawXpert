import mysql.connector

def get_db_connection():
    connection = mysql.connector.connect(
        host='127.0.0.1',  
        port=3306,        
        user='root',
        password='Bhoomi31',
        database='legal_guidance'
    )
    return connection
 