from flask import Flask, request, jsonify, render_template
import boto3  # The AWS SDK for Python
import config
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer, util
from numpy import dot
from numpy.linalg import norm

app = Flask(__name__)

# Declare a constant variable
TARGET_LANGUAGE_CODE = 'en'
SOURCE_LANGUAGE_CODE = 'ko'

# 유사도 기준 점수
SIMILARITY_CRITERION_POINT = -0.01

# Configure AWS Translate client
translate = boto3.client(service_name='translate',
                         aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                         aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                         region_name=config.AWS_SEOUL_REGION)


def get_mongo_client():
    username = config.MONGODB_USERNAME
    password = config.MONGODB_PASSWORD
    host = config.MONGODB_HOST
    port = config.MONGODB_PORT

    # Create a MongoDB connection URI
    mongo_uri = f"mongodb://{username}:{password}@{host}:{port}/"

    # Create the MongoDB client and return it
    return MongoClient(mongo_uri)


def cos_sim(num1, num2):
    return dot(num1, num2) / (norm(num1) * norm(num2))


@app.route('/')
def index():
    mongo_client = get_mongo_client()
    menjil_db = mongo_client['menjil']
    qa_col = menjil_db['qa_list']
    results = qa_col.find()

    return render_template('mongo.html', data=results)


@app.route('/api/chat/flask', methods=['GET'])
# @app.route('/api/chat/flask', methods=['POST'])
#
# Spring Boot에서 데이터를 받아온다: 멘토 닉네임, 멘티 닉네임, 원본 질문, 세 줄 요약된 질문(by ChatGPT)
#
def message_from_spring_boot():
    """ Declare variables """
    # mentor_nickname = None
    # mentee_nickname = None
    # question_origin = None
    # question_summary = None  # 한글 요약본
    mentor_nickname = "멘토짱"
    mentee_nickname = "멘티짱"
    question_origin = "안녕하세요. 멘티짱 입니다. 풀스택 개발자가 되려면 뭐부터 하는게 좋을까요? 프로젝트는 얼마나 어떻게 해야할까요?"
    question_summary = "풀스택 개발자가 되려면 뭐부터 하는게 좋을까요? 프로젝트는 얼마나 어떻게 해야할까요?"

    # try:
    #     """ Get data from Spring Boot Server """
    #     data = request.get_json()
    #     mentor_nickname = data['mentor_nickname']
    #     mentee_nickname = data['mentee_nickname']
    #     question_origin = data['question_origin']
    #     question_summary = data['question_summary']
    #
    # except Exception as e:
    #     return jsonify({'error': str(e)}), 500

    #
    # 받아온 데이터 중, 세 줄 요약된 질문을 AWS Translate API를 통해 영어로 번역
    #
    translation_response = translate.translate_text(Text=question_summary, SourceLanguageCode=SOURCE_LANGUAGE_CODE,
                                                    TargetLanguageCode=TARGET_LANGUAGE_CODE)
    # Extract the translated text from the response: 영어 요약본
    translated_QS = translation_response['TranslatedText']

    #
    # MongoDB 연결
    #
    mongo_client = get_mongo_client()
    menjil_db = mongo_client['menjil']
    qa_col = menjil_db['qa_list']

    #
    # qa_list collection에 접근해서, Spring Boot에서 받아온 정보(멘토 닉네임, 멘티 닉네임, 원본 질문, 세 줄 요약된 질문) 와 영어 번역본을 먼저 저장
    #
    send_data = {
        'mentee_nickname': mentee_nickname,
        'mentor_nickname': mentor_nickname,
        'question_origin': question_origin,
        'question_summary': question_summary,
        'question_summary_en': translated_QS,
    }
    # 비교를 위하여 기존의 질문을 mongodb에 저장
    # insert = qa_col.insert_one(send_data)
    # print(insert)

    #
    # 멘토가 답변한 내역이 있는 문답 데이터를 모두 불러온다.
    #
    data = []
    for document in qa_col.find(
            {'mentor_nickname': mentor_nickname, 'answer': {'$exists': True, '$ne': None}}, {'question_origin': False}
    ):
        data.append(document)
        # print(document)
    if len(data) < 1:
        # 멘토가 받은 질문에 답변한 질문이 하나도 없을 경우 스프링에 에러 전송
        print("멘토가 답변한 질문이 없습니다")

    #
    # 세 줄 요약된 질문들을 영어로 각각 번역
    #
    '''(패스)이미 저장할 때 번역함'''

    #
    # 문장 유사도 검증
    #
    # 1. 유사도 계산
    data_QSE_list = [doc['question_summary_en'] for doc in data]
    for idx, qe in enumerate(data_QSE_list):
        print(f'질문{idx + 1}: {qe}')
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    query_embedding = model.encode(translated_QS)
    passage_embedding = model.encode(data_QSE_list)
    dot_score = util.dot_score(query_embedding, passage_embedding)
    dot_score_list = dot_score.tolist()[0]
    # print("Similarity:", dot_score_list)

    # 2. 계산된 데이터 중 유사도 상위 3개 데이터 추출
    similarity_list = [{'similarity': -1.0}, {'similarity': -1.0}, {'similarity': -1.0}]
    for doc, score in zip(data, dot_score_list):
        doc['similarity'] = score
        sim_list = [d['similarity'] for d in similarity_list]
        if score > min(sim_list):
            idx_min = sim_list.index(min(sim_list))
            similarity_list[idx_min] = doc

    # 3. 유사도 점수가 기준 점수(SIMILARITY_CRITERION_POINT) 이하인 데이터 삭제
    result_similarity_list = []
    for doc in similarity_list:
        if doc['similarity'] > SIMILARITY_CRITERION_POINT:
            result_similarity_list.append(doc)
    print("---------------유사도 상위 3개 데이터---------------")
    for doc in result_similarity_list:
        print(doc)


    #
    # 기존의 질문을 mongodb에 저장하고, 답변이 올 때까지 기다린다. 답변 오면 update 처리 <- 이건 스프링 부트에서.
    #
    # 1. 클라이언트가 1,2,3 유사도 질문으로 만족 혹은 만족을 못해서 직접 질문을 등록하는 상태 결과를 스프링에서 받음
    return jsonify({'error': 'ho'})
    # 2. 질문을 직접 등록하면 위에서 저장한 채로 넘어가고 만족을 했다면 클라이언트의 저장된 질문 데이터를 삭제


if __name__ == '__main__':
    app.run(debug=True)
