#!/usr/bin/env python3
"""
성장미션 데이터 분석 및 시각화
"""
import re
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime

# 한글 폰트 설정 (Mac용)
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

def parse_missions(filepath):
    """성장미션 파일 파싱"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    missions = []
    current_mission = None
    
    # 미션 번호별로 분리
    mission_blocks = re.split(r'(성장미션 #\d+)', content)
    
    for i in range(1, len(mission_blocks), 2):
        if i + 1 < len(mission_blocks):
            mission_header = mission_blocks[i]
            mission_content = mission_blocks[i + 1]
            
            # 미션 번호 추출
            mission_num_match = re.search(r'#(\d+)', mission_header)
            if not mission_num_match:
                continue
            
            mission_num = int(mission_num_match.group(1))
            
            # 날짜 추출
            date_match = re.search(r'(\d{4}년\s*\d{1,2}/\d{1,2}|\d{4}년\s*\d{1,2}월\s*\d{1,2}|202\d년 \d{1,2}/\d{1,2})', mission_content)
            date_str = date_match.group(1) if date_match else ""
            
            # 참여자 추출 (1. 이름, 2. 이름 등)
            # "년", "월", "일" 등 날짜 관련 단어 제외
            participants_raw = re.findall(r'^\d+[\.\s]*([가-힣]+)', mission_content, re.MULTILINE)
            participants = [p for p in participants_raw if p not in ['년', '월', '일'] and len(p) >= 2]
            
            # 활동 추출 (- 로 시작하는 라인)
            activities_raw = re.findall(r'^-\s*(.+)$', mission_content, re.MULTILINE)
            # "--" 같은 구분선 제거 및 실제 활동만 필터
            activities = [a.strip() for a in activities_raw if a.strip() and a.strip() != '-' and a.strip() != '--' and len(a.strip()) > 1]
            
            missions.append({
                'number': mission_num,
                'date': date_str,
                'participants': participants,
                'activities': activities,
                'participant_count': len(participants)
            })
    
    return sorted(missions, key=lambda x: x['number'], reverse=True)

def categorize_activity(activity):
    """활동을 카테고리로 분류 - 통합 버전"""
    activity_lower = activity.lower()
    
    # 빈 문자열이나 구분선 제외
    if not activity.strip() or activity.strip() in ['--', '-']:
        return '구분선'
    
    # 1. 운동/건강
    if any(word in activity_lower for word in ['러닝', '운동', '크로스핏', '헬스', '산책', '걷기', '유산소', '근력', '스트레칭', '명상', '요가', '필라테스', '발차기', '철봉', '조정', '경보', '흉곽호흡', '호흡', '수면', '잠', '취침', '딥슬립', '체력', '컨디션']):
        return '운동/건강'
    
    # 2. 학습 (모든 학습 관련 통합)
    if any(word in activity_lower for word in [
        # 독서/논문
        '독서', '읽기', '논문', '책', '리포트', 'report', 'wsj', '롱블랙', '뉴스', '요약',
        # 온라인 학습
        '듀오링고', '인강', '강의', '수업', '온라인',
        # 공부/시험
        '공부', '학습', '복습', '과제', '시험', '문제', 'math', '검진', '중간과제',
        # 언어
        '영어', '회화', '스픽', '말해보카', '유튜브 듣기'
    ]):
        return '학습'
    
    # 3. 업무/프로젝트 (모든 업무 관련 통합)
    if any(word in activity_lower for word in [
        # AI/ML
        'ai', 'agent', '에이전트', '모델', 'ml', '머신러닝', '알고리즘', '전략', '알파', 
        'nanobanana', '훈련', '실험', 'rag', 'llm', 'crypto', 'trading', 'quant', '퀀트', 
        '헤지펀드', '백테스팅', 'convex', 'optimization',
        # 개발
        '코드', '개발', '구현', '프로젝트', '해커톤', 'github', 'cli', 'workflow', 
        'ui', 'ux', '피그마', 'figma', 'tester', '블로그', 'polars', 'gemini', 'claude',
        # 커리어
        '이력서', '면접', '포트폴리오', '지원', '경력', '회사', '업무', '미팅', 
        '링크드인', 'linkedin', '커피챗', '커리어', 'tf', '출근',
        # 발표/연구
        '발표', '자료', '리서치', '분석', '스터디', '세미나', 'pitch', 'deck', 
        '교육', '온보딩', '컨설턴트', '학회', '컨퍼런스'
    ]):
        return '업무/프로젝트'
    
    # 4. 일상/생활 (모든 일상 관련 통합)
    if any(word in activity_lower for word in [
        # 식사/건강
        '식단', '과일', '음식', '먹기', '요거트', '스무디', '즙', '영양', '탄수', 
        '저탄', '치팅데이', '식사', '밥', '레몬', '올리브', '치킨', '쿠키', '마녀스프',
        # 생활관리
        '청소', '정리', '집', '이사', '인테리어', '빨래', '짐', '옷장', '대청소', '준비', '화장실',
        # 기록/성찰
        '일기', '감사', '기록', '회고', '성찰', '계획', '플랜', '일정', '가계부', '투자'
    ]):
        return '일상/생활'
    
    # 5. 여가/취미
    if any(word in activity_lower for word in ['여행', '영화', '음악', '콘텐츠', '봉사', '모임', '파티', '임장', '탐사', '쇼핑', '보컬', '노래', '취미', '필사', '캠핑', '리트릿', '송년회', '뒷풀이']):
        return '여가/취미'
    
    # 6. 기타
    return '기타'

def anonymize_name(name, name_map):
    """이름을 익명화"""
    if name not in name_map:
        name_map[name] = f"참여자{len(name_map) + 1}"
    return name_map[name]

# 데이터 파싱
missions = parse_missions('성장미션_최종본_200to100.txt')

print(f"총 {len(missions)}개 미션 파싱 완료")
print(f"미션 범위: #{missions[0]['number']} ~ #{missions[-1]['number']}")

# 1) 참여인원별 개수 (익명화)
name_map = {}
all_participants = []
for mission in missions:
    for p in mission['participants']:
        all_participants.append(p)

participant_counts = Counter(all_participants)

# 익명화된 이름으로 변환
anonymous_counts = {}
for name, count in participant_counts.most_common():
    anon_name = anonymize_name(name, name_map)
    anonymous_counts[anon_name] = count

# 2) 카테고리별 분류
all_activities = []
for mission in missions:
    for activity in mission['activities']:
        category = categorize_activity(activity)
        all_activities.append(category)

category_counts = Counter(all_activities)

# 3) 시계열 데이터 (미션 번호별 참여 인원 수)
timeline_data = []
for mission in sorted(missions, key=lambda x: x['number']):
    if 100 <= mission['number'] <= 200:
        timeline_data.append({
            'mission': mission['number'],
            'count': mission['participant_count']
        })

# 그래프 생성
fig, axes = plt.subplots(3, 1, figsize=(14, 16))
fig.suptitle('15조 성장미션 데이터 분석 (#200~#100)', fontsize=18, fontweight='bold')

# 1) 참여인원별 개수
ax1 = axes[0]
names = list(anonymous_counts.keys())
counts = list(anonymous_counts.values())
colors = plt.cm.Set3(np.linspace(0, 1, len(names)))
bars1 = ax1.bar(names, counts, color=colors, edgecolor='black', linewidth=1.2)
ax1.set_xlabel('참여자 (익명)', fontsize=12, fontweight='bold')
ax1.set_ylabel('참여 횟수', fontsize=12, fontweight='bold')
ax1.set_title('1) 참여자별 참여 횟수', fontsize=14, fontweight='bold', pad=20)
ax1.grid(axis='y', alpha=0.3, linestyle='--')
ax1.set_xticklabels(names, rotation=45, ha='right')

# 막대 위에 숫자 표시
for bar in bars1:
    height = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., height,
             f'{int(height)}',
             ha='center', va='bottom', fontweight='bold', fontsize=10)

# 2) 카테고리별 히스토그램
ax2 = axes[1]
categories = list(category_counts.keys())
cat_counts = list(category_counts.values())
colors2 = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']
bars2 = ax2.barh(categories, cat_counts, color=colors2[:len(categories)], edgecolor='black', linewidth=1.2)
ax2.set_xlabel('활동 개수', fontsize=12, fontweight='bold')
ax2.set_ylabel('카테고리', fontsize=12, fontweight='bold')
ax2.set_title('2) 활동 카테고리별 분포', fontsize=14, fontweight='bold', pad=20)
ax2.grid(axis='x', alpha=0.3, linestyle='--')

# 막대 끝에 숫자 표시
for bar in bars2:
    width = bar.get_width()
    ax2.text(width, bar.get_y() + bar.get_height()/2.,
             f'{int(width)}',
             ha='left', va='center', fontweight='bold', fontsize=11, 
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='gray', alpha=0.8))

# 3) 시계열 그래프
ax3 = axes[2]
mission_numbers = [d['mission'] for d in timeline_data]
participant_counts_time = [d['count'] for d in timeline_data]

# 실제 데이터 플롯
ax3.plot(mission_numbers, participant_counts_time, marker='o', linewidth=2.5, 
         markersize=6, color='#3498db', markerfacecolor='#e74c3c', 
         markeredgewidth=1.5, markeredgecolor='white', label='실제 참여 인원', alpha=0.8)
ax3.fill_between(mission_numbers, participant_counts_time, alpha=0.2, color='#3498db')

# 5일 이동평균 계산 및 플롯
window = 5
if len(participant_counts_time) >= window:
    moving_avg = []
    for i in range(len(participant_counts_time)):
        if i < window - 1:
            # 처음 몇 개는 가능한 데이터로만 평균
            moving_avg.append(np.mean(participant_counts_time[:i+1]))
        else:
            moving_avg.append(np.mean(participant_counts_time[i-window+1:i+1]))
    
    ax3.plot(mission_numbers, moving_avg, linewidth=3, color='#e67e22', 
             linestyle='-', alpha=0.9, label='5일 이동평균')

ax3.set_xlabel('미션 번호', fontsize=12, fontweight='bold')
ax3.set_ylabel('참여 인원 수', fontsize=12, fontweight='bold')
ax3.set_title('3) 미션 번호별 참여 인원 수 추이 (#100~#200)', fontsize=14, fontweight='bold', pad=20)
ax3.grid(True, alpha=0.3, linestyle='--')
ax3.set_xlim(100, 200)
ax3.legend(loc='upper right', fontsize=10, framealpha=0.9)

plt.tight_layout()
plt.savefig('성장미션_분석_그래프.png', dpi=300, bbox_inches='tight')
print("\n✅ 그래프 저장 완료: 성장미션_분석_그래프.png")

# 통계 출력
print("\n" + "="*50)
print("📊 데이터 분석 결과")
print("="*50)
print(f"\n【참여자 통계】")
print(f"총 참여자 수: {len(participant_counts)}명")
print(f"총 참여 기록: {sum(participant_counts.values())}건")
for name, count in sorted(participant_counts.items(), key=lambda x: -x[1])[:10]:
    anon = anonymize_name(name, name_map)
    print(f"  {anon} ({name}): {count}회")

print(f"\n【카테고리 통계】")
for cat, count in category_counts.most_common():
    percentage = count / len(all_activities) * 100
    print(f"  {cat}: {count}개 ({percentage:.1f}%)")

print(f"\n【참여 인원 추이】")
avg_count = np.mean(participant_counts_time)
print(f"  평균 참여 인원: {avg_count:.2f}명")
print(f"  최대 참여 인원: {max(participant_counts_time)}명")
print(f"  최소 참여 인원: {min(participant_counts_time)}명")

print("\n✅ 분석 완료!")

