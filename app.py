from flask import Flask, request, jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

app = Flask(__name__)

# 이메일 설정
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your-email@gmail.com"  # 발신용 Gmail 계정
SMTP_PASSWORD = "your-app-password"  # Gmail 앱 비밀번호
ADMIN_EMAIL = "ganga0314@gmail.com"  # 관리자 이메일

@app.route('/send-chat-email', methods=['POST'])
def send_chat_email():
    try:
        data = request.json
        student_code = data.get('studentCode')
        chat_content = data.get('chatContent')
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

        # 이메일 내용 구성
        subject = f"[AI 상담 기록] 학생코드: {student_code} - {date}"
        
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = subject

        body = chat_content
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # 이메일 전송
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        return jsonify({"success": True, "message": "이메일이 성공적으로 전송되었습니다."})

    except Exception as e:
        print(f"이메일 전송 오류: {str(e)}")
        return jsonify({"success": False, "message": "이메일 전송에 실패했습니다."}), 500

# ... 기존 라우트들 ...