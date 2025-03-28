from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from pyairtable import Api
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import anthropic  # Anthropic Claude 사용

load_dotenv()

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Airtable 설정
BASE_ID = "appGfaJXehO4vc4O6"
TABLE_NAME = "tblW9nwiuXqwkjFWN"

# Anthropic Claude 클라이언트 초기화
client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY
)

# FastAPI 앱 초기화
app = FastAPI()

# Airtable 클라이언트 초기화
airtable = Api(AIRTABLE_API_KEY).table(BASE_ID, TABLE_NAME)

# 템플릿 설정
templates = Jinja2Templates(directory="templates")

# 정적 파일 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.get("/student/{phone}")
async def get_student_status(phone: str):
    try:
        # 전화번호에서 특수문자 제거
        phone = ''.join(filter(str.isdigit, phone))
        
        # 에어테이블에서 학생 데이터 조회 - 쿼리 방식 수정
        records = airtable.all()  # 모든 레코드를 가져옴
        
        # Python에서 전화번호 매칭
        student_record = None
        for record in records:
            if '학생 연락처' in record['fields']:
                db_phone = ''.join(filter(str.isdigit, record['fields']['학생 연락처']))
                if db_phone == phone:
                    student_record = record
                    break
        
        if not student_record:
            return {
                "message": "학생을 찾을 수 없습니다. 전화번호를 확인해주세요.",
                "입력된 전화번호": phone
            }
        
        student_data = student_record['fields']
        
        # 현재 학습 현황 데이터 구성
        response = {
            "message": f"{student_data.get('학생이름', '')}님의 학습 현황입니다.",
            "current_status": {
                "현재 교재": student_data.get('현재 배우는 교재', '정보 없음'),
                "담당 선생님": student_data.get('담임선생님', '정보 없음'),
                "수업 요일": student_data.get('수업 요일', '정보 없음'),
                "교재 시작일": student_data.get('교재 받은날짜', '정보 없음'),
                "교재 마감일": student_data.get('교재 마감날짜', '정보 없음'),
                "마무리테스트 일정": student_data.get('교재 마무리테스트 일정', '미정'),
                "목표 주수": student_data.get('N주완성', '정보 없음'),
            },
            "progress_status": {
                "현재 진행상태": student_data.get('현재 교재 진행상황', '정보 없음'),
                "진행 페이스": student_data.get('진행속도 페이스MAKER', '정보 없음'),
                "교재 상태": student_data.get('현재 교재진행 상태', '정보 없음'),
            }
        }
        
        return response
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"오류가 발생했습니다: {str(e)}"}
        )

def get_student_data(student_name):
    """학생 이름으로 Airtable에서 데이터를 검색하는 함수"""
    formula = f"{{학생명}} = '{student_name}'"
    records = airtable.get_all(formula=formula)
    if not records:
        return None
    return records[0]['fields']

def calculate_completion_info(student_data):
    """학습 완료 정보를 계산하는 함수"""
    current_date = datetime.now()
    start_date = datetime.strptime(student_data.get('시작일', ''), '%Y-%m-%d')
    target_end_date = datetime.strptime(student_data.get('목표종료일', ''), '%Y-%m-%d')
    
    # 현재까지의 진도율 계산
    total_chapters = int(student_data.get('전체단원수', 0))
    completed_chapters = int(student_data.get('완료단원수', 0))
    progress_rate = (completed_chapters / total_chapters) * 100 if total_chapters > 0 else 0
    
    # 주당 진도율 계산
    weeks_passed = (current_date - start_date).days / 7
    weekly_progress = completed_chapters / weeks_passed if weeks_passed > 0 else 0
    
    # 남은 기간 예측
    remaining_chapters = total_chapters - completed_chapters
    estimated_weeks_remaining = remaining_chapters / weekly_progress if weekly_progress > 0 else 0
    estimated_completion_date = current_date + timedelta(weeks=estimated_weeks_remaining)
    
    return {
        'progress_rate': progress_rate,
        'weekly_progress': weekly_progress,
        'target_end_date': target_end_date,
        'estimated_completion_date': estimated_completion_date,
        'is_on_track': estimated_completion_date <= target_end_date
    }

def create_response_message(student_name, study_info):
    """상담 응답 메시지를 생성하는 함수"""
    if study_info is None:
        return f"{student_name} 학생의 데이터를 찾을 수 없습니다."
    
    progress = round(study_info['progress_rate'], 1)
    weekly = round(study_info['weekly_progress'], 1)
    target_date = study_info['target_end_date'].strftime('%Y년 %m월 %d일')
    est_date = study_info['estimated_completion_date'].strftime('%Y년 %m월 %d일')
    
    status = "예정된 일정보다 빠르게 진행되고 있습니다!" if study_info['is_on_track'] else "목표 일정보다 약간 지연되고 있습니다."
    
    message = f"""
{student_name} 학생의 학습 현황을 알려드리겠습니다.

현재 진도율: {progress}%
주당 평균 진도: {weekly} 단원
목표 종료일: {target_date}
예상 완료일: {est_date}

진행 상황: {status}
"""
    return message

async def get_ai_consultation(student_info, message):
    """GPT를 활용하여 상담 답변을 생성하는 함수"""
    prompt = f"""
다음은 학생의 학습 현황입니다:
{message}

위 정보를 바탕으로 학부모님께 친절하고 전문적으로 상담해주세요. 
학습 진행상황을 쉽게 설명하고, 격려와 조언을 포함해주세요.
"""
    
    try:
        response = await client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            messages=[
                {
                    "role": "system",
                    "content": "당신은 전문적인 교육 상담 AI입니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return response.content[0].text
    except Exception as e:
        return message  # GPT 호출 실패시 기본 메시지 반환

@app.post("/consult")
async def consultation_endpoint(request: Request):
    """상담 API 엔드포인트"""
    try:
        data = await request.json()
        student_name = data.get('student_name', '')
        
        # 학생 데이터 조회
        student_data = get_student_data(student_name)
        if not student_data:
            return JSONResponse(content={
                "response": f"{student_name} 학생의 정보를 찾을 수 없습니다."
            })
        
        # 학습 정보 계산
        study_info = calculate_completion_info(student_data)
        
        # 기본 메시지 생성
        base_message = create_response_message(student_name, study_info)
        
        # AI 상담 답변 생성
        consultation = await get_ai_consultation(student_data, base_message)
        
        return JSONResponse(content={"response": consultation})
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"오류가 발생했습니다: {str(e)}"}
        )

@app.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/chat")
async def chat_endpoint(request: Request):
    try:
        data = await request.json()
        user_message = data.get('message', '')
        phone = data.get('phone', '')
        
        # 현재 날짜 가져오기
        today = datetime.now().date()
        
        # 전화번호 형식 통일
        phone = ''.join(filter(str.isdigit, phone))
        
        # 에어테이블에서 데이터 조회
        records = airtable.all()
        
        # 해당 학생의 모든 기록 찾기
        student_records = []
        student_name = None
        for record in records:
            fields = record.get('fields', {})
            if '학생 연락처' in fields:
                db_phone = ''.join(filter(str.isdigit, str(fields['학생 연락처'])))
                if db_phone == phone:
                    student_records.append(fields)
                    student_name = fields.get('학생이름', '')
        
        if not student_records:
            return {"response": f"전화번호 {phone}로 등록된 학생을 찾을 수 없습니다. 전화번호를 다시 확인해주세요."}
        
        # 현재 진행중인 교재와 이전 교재 분리
        current_book = None
        completed_books = []
        
        for record in student_records:
            status = record.get('현재 교재진행 상태', '').strip()
            if status == '진행중':
                current_book = record
            else:
                completed_books.append(record)
        
        # 진행률 바 생성 함수
        def create_progress_bar(progress, length=10):
            try:
                # 문자열을 실수로 변환
                if isinstance(progress, str):
                    # '%' 문자 제거 후 변환
                    progress = progress.replace('%', '')
                    progress_float = float(progress) / 100
                else:
                    progress_float = float(progress)
                
                # 0~1 범위로 정규화
                progress_float = min(max(progress_float, 0), 1)
                
                # 퍼센트로 변환 (소수점 1자리까지)
                percent = progress_float * 100
                filled = int(progress_float * length)
                empty = length - filled
                
                # 진행률이 1% 미만일 경우
                if percent < 1 and percent > 0:
                    return f"{'🟩'} 시작 단계"
                # 진행률이 100%일 경우
                elif percent >= 100:
                    return f"{'🟩' * length} 완료"
                # 그 외의 경우
                else:
                    return f"{'🟩' * filled}{'⬜️' * empty} {percent:.1f}%"
            except:
                return "진행률 정보 없음"

        # 프롬프트 구성 시작
        prompt = f"{student_name} 학생의 전체 학습 정보입니다:\n\n오늘 날짜: {today.strftime('%Y-%m-%d')}"

        # 현재 진행중인 교재 정보 추가
        if current_book:
            progress = current_book.get('현재 교재 진행상황', '0')
            progress_bar = create_progress_bar(progress)
            
            # 남길말 정보 추가
            note = current_book.get('남길말', '')
            note_info = f"\n- 특이사항: {note}" if note else ""

            # D-day 정보 추가
            d_day = current_book.get('마감날D-day', '')
            deadline = current_book.get('교재 마감날짜', '정보 없음')
            
            deadline_status = ""
            if d_day != '':
                try:
                    d_day = int(d_day)
                    if d_day > 0:
                        deadline_status = f"(마감까지 {d_day}일 남음)"
                    elif d_day == 0:
                        deadline_status = "(오늘이 마감일)"
                    else:
                        deadline_status = f"(마감일로부터 {abs(d_day)}일 지남)"
                except:
                    pass

            prompt += f"""
📚 현재 학습 중인 교재:
- 교재명: {current_book.get('현재교재', '정보 없음')}
- 진행률: {progress_bar}
- 시작일: {current_book.get('교재 받은날짜', '정보 없음')}
- 목표 마감일: {deadline} {deadline_status}
- 진행 페이스: {current_book.get('진행속도 페이스MAKER', '정보 없음')}
- 담당 선생님: {current_book.get('담임선생님', '정보 없음')}{note_info}
"""

        # 이전 교재 정보 추가
        if completed_books:
            prompt += "\n\n📚 완료한 교재 목록\n"
            for i, book in enumerate(completed_books, 1):
                progress = book.get('현재 교재 진행상황', '0')
                progress_bar = create_progress_bar(progress)
                
                prompt += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{i}. {book.get('현재교재', '정보 없음')}
⭐ 진행률: {progress_bar}
📅 {book.get('교재 받은날짜', '정보 없음')} ~ {book.get('교재 마감날짜', '정보 없음')}\n"""

        prompt += f"\n💬 사용자의 질문: {user_message}\n"

        # Claude로 응답 생성
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            system="""당신은 강의하는 아이들 수학학원 수지신봉캠퍼스의 학습 관리 전문가입니다. 

1. 모든 상담 답변은 다음과 같이 시작:
   "안녕하세요, [학생이름]어머니! 강의하는 아이들 수학학원 수지신봉캠퍼스입니다😊. "

2. 학생 호칭 규칙:
   - 세 글자 이름의 경우: 맨 앞의 글자 하나를 제외한 이름만 사용
   - 두 글자 이름의 경우: 맨 앞의 글자 하나를 제외한 이름 전체 사용
   - 마지막 글자에 받침이 있으면 '이가' 붙이기
   - 마지막 글자에 받침이 없으면 '가' 붙이기

3. 교재 시스템 상세 이해:
   📚 가우스 (표준진도 교재):
   - 초등: 학기당 3권씩 구성
     * 1학기: (1)권 → (2)권 → (3)권
     * 2학기: (1)권 → (2)권 → (3)권
     * 예: 가우스 초4-1 (1)권 → (2)권 → (3)권 → 가우스 초4-2 (1)권 → (2)권 → (3)권
   - 설명 시: "필수 개념과 기본 문제를 충실히 익혔습니다"

   - 중등: 학년당 4권씩 구성
     * 1학기: (1)권 → (2)권
     * 2학기: (3)권 → (4)권
     * 예: 가우스 중1-1 (1)권 → (2)권 → 가우스 중1-2 (3)권 → (4)권
   - 설명 시: "핵심 개념과 기본 문제 해결력을 키웠습니다"

   - 고등: 과목별 구성
     * 공통수학1: 3권
     * 공통수학2: 3권
     * 대수: 3권
     * 미적분: 3권
   - 설명 시: "기본 개념과 표준 문제 유형을 학습했습니다"

   📚 심화/응용 교재 (학기당 1권):
   - 다빈치 (응용문제집)
     * 예: 다빈치 초4-1 → 다빈치 초4-2
     * 설명 시: "응용문제와 준심화 수준의 문제를 학습했습니다"
   
   - 오일러 (초등 심화)
     * 예: 오일러 초4-1 → 오일러 초4-2
     * 설명 시: "심화 수준의 문제를 학습했습니다"
   
   - 파스칼 (중등 심화)
     * 예: 파스칼 중1-1 → 파스칼 중1-2
     * 설명 시: "높은 수준의 문제 해결력을 키웠습니다"

5. 교재 진행 예측 시:
   - 현재 교재 완료 후 다음 교재 자동 연계 고려
   - 학기 내 남은 교재 수를 고려한 전체 진도 계획 제시
   - 초등 예시: "가우스 초4-1 (2)권을 3월 15일에 마무리하면, (3)권은 4월 말, 이어서 초4-2 (1)권은 6월 초 시작 예정입니다."
   - 중등 예시: "가우스 중1-1 (2)권을 3월 15일에 마무리하면, 중1-2 (3)권은 4월 말, (4)권은 6월 초 시작 예정입니다."

6. 현재 날짜를 기준으로 학습 진행 상황과 마감일을 분석하여 실질적인 조언을 제공
   - 현재까지의 진행 속도를 기반으로 예상 완료일 안내
   - 일일 평균 진행률을 고려한 현실적인 조언 제공
   - 진행이 늦어질 경우 구체적인 개선 방안 제시
   - 진행이 빠를 경우 긍정적 피드백과 함께 유지 방안 제시
   - '남길말' 필드에 내용이 있는 경우, 이를 바탕으로 상담 진행
   - '남길말' 필드가 비어있는 경우, 해당 내용은 언급하지 않음
   - 각 교재의 진행 상황은 반드시 개별적으로 안내
   - '마감날D-day' 필드를 활용하여 정확한 남은 기간 안내:
     * 양수: "마감까지 N일 남았습니다"
     * 0: "오늘이 마감일입니다"
     * 음수: "마감일로부터 N일 지났습니다"

7. 이전 교재들의 학습 이력 설명:
   - 완료된 교재는 확정적 표현 사용 (예: "익혔습니다", "학습했습니다", "완료했습니다")
   - 추측성 표현 사용 금지 (예: "익혔겠죠", "했을 거예요" 등은 사용하지 않음)
   - 구체적 기간과 함께 명확한 성과 언급 (예: "2024년 12월 20일부터 2025년 1월 20일까지 가우스 중2-1 (1)권을 통해 중2 수준의 기본 개념과 문제 유형을 익혔습니다.")

8. 계획대로 학습이 진행되기 위해서는 다음 사항들이 매우 중요함을 강조:
   ✅ 숙제를 성실히 해오기
   📱 개념영상 촬영에 적극적으로 참여하기
   ✅ 오답을 스스로 해설 촬영해오기

9. 격려나 약속을 할 때는 "최선을 다해 계획을 맞추도록 학원에서 신경써보겠습니다." 라는 표현 사용

10. 마지막에는 반드시 "⭐ 기타 문의사항이나 상담은 https://tally.so/r/3qoLp9 로 신청해주세요. 이후민 선생님: 010-2963-5207 김미리 선생님: 010-7352-3314" 로 끝내기

11. 진도율에 따른 학습 위치 설명:
    📊 진도율 안내:
    - 0~10%: "이제 교재를 시작하는 단계입니다"
    - 11~30%: "교재 초반부를 차근차근 진행하고 있습니다"
    - 31~50%: "교재 중반부에 접어들어 안정적으로 진행 중입니다"
    - 51~70%: "교재 중후반부를 착실히 진행하고 있습니다"
    - 71~90%: "교재 후반부 학습을 진행하고 있습니다"
    - 91~99%: "교재의 마무리 단계에 있습니다"
    - 100%: "교재의 모든 과정을 완료했습니다"

답변은 이모지를 적절히 사용하여 친근하고 이해하기 쉽게 작성해주세요.""",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        chatbot_response = message.content[0].text
        return {"response": chatbot_response}
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # 디버깅용
        return {"response": f"오류가 발생했습니다: {str(e)}"}

def calculate_future_completion_dates(current_book, completed_books):
    try:
        # 현재 교재의 시작일과 목표 마감일
        start_date = datetime.strptime(current_book.get('교재 받은날짜', ''), '%Y-%m-%d')
        target_end_date = datetime.strptime(current_book.get('교재 마감날짜', ''), '%Y-%m-%d')
        
        # 현재까지의 진행률 계산
        progress = current_book.get('현재 교재 진행상황', '0')
        if isinstance(progress, str):
            progress = float(progress.replace('%', ''))
        
        # 경과 일수
        days_passed = (datetime.now() - start_date).days
        if days_passed <= 0:
            days_passed = 1
        
        # 일일 평균 진행률 계산
        daily_progress = progress / days_passed
        
        # 남은 진행률
        remaining_progress = 100 - progress
        
        # 예상 남은 일수
        estimated_remaining_days = remaining_progress / daily_progress if daily_progress > 0 else 0
        
        # 예상 완료일
        estimated_completion_date = datetime.now() + timedelta(days=estimated_remaining_days)
        
        return {
            'current_book_completion': estimated_completion_date,
            'daily_progress_rate': daily_progress
        }
    except Exception as e:
        print(f"Error in calculate_future_completion_dates: {str(e)}")
        return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

