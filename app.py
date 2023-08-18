import boto3  # The AWS SDK for Python
from flask import Flask, request, jsonify, render_template
from numpy import dot
from numpy.linalg import norm
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer, util

import config

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


@app.route('/api/chat/flask', methods=['POST'])
def message_from_spring_boot():
    """ Declare variables """
    mentor_nickname = None
    mentee_nickname = None
    question_origin = None
    question_summary = None  # 원본 질문 세 줄 요약본

    try:
        """ Get data from Spring Boot Server """
        data = request.get_json()
        mentor_nickname = data['mentor_nickname']
        mentee_nickname = data['mentee_nickname']
        question_origin = data['question_origin']
        question_summary = data['question_summary']
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    """ 받아온 데이터 중, 세 줄 요약된 질문을 AWS Translate API를 통해 영어로 번역 """
    translation_response = translate.translate_text(Text=question_summary, SourceLanguageCode=SOURCE_LANGUAGE_CODE,
                                                    TargetLanguageCode=TARGET_LANGUAGE_CODE)

    """ Extract the translated text from the response """
    translated_summary_text_en = translation_response['TranslatedText']

    """ Connect MongoDB """
    mongo_client = get_mongo_client()
    menjil_db = mongo_client['menjil']
    qa_list_collection = menjil_db['qa_list']

    """qa_list collection에 접근해서, Spring Boot에서 받아온 정보(멘토 닉네임, 멘티 닉네임, 원본 질문, 세 줄 요약된 질문)와 영어 번역본을 먼저 저장"""
    document = {
        # 마지막에 붙는 '\n' 제거
        'mentee_nickname': mentee_nickname,
        'mentor_nickname': mentor_nickname,
        'question_origin': question_origin[:-1] if question_origin.endswith('\n') else question_origin,
        'question_summary': question_summary[:-1] if question_summary.endswith('\n') else question_summary,
        'question_summary_en': translated_summary_text_en[:-1] if translated_summary_text_en.endswith('\n')
        else translated_summary_text_en,
        'answer': None
    }
    insert = qa_list_collection.insert_one(document)  # save a document

    """ 멘토가 답변한 내역이 있는 문답 데이터를 모두 불러온다 """
    filter_ = {
        'mentor_nickname': mentor_nickname,
        'answer': {'$exists': True, '$ne': None}
    }
    projection_ = {
        'mentee_nickname': False,
        'mentor_nickname': False,
        'question_origin': False
    }
    # Retrieve the documents and store them in the data list
    data = list(qa_list_collection.find(filter_, projection_))
    print('data: ', data)

    """ 답변 개수가 3개 미만일 경우, 빈 리스트를 Spring Boot로 리턴"""
    if len(data) < 3:
        return []

    """ 문장 유사도 검증 """
    """ 1. 유사도 검사"""
    question_summary_en_list = [doc['question_summary_en'] for doc in data]
    # for idx, qe in enumerate(question_summary_en_list):
    #     print(f'질문{idx + 1}: {qe}')

    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    query_embedding = model.encode(translated_summary_text_en)
    passage_embedding = model.encode(question_summary_en_list)
    dot_score = util.dot_score(query_embedding, passage_embedding)
    dot_score_list = dot_score.tolist()[0]

    """ 2. 계산된 데이터 중 유사도 상위 3개 데이터 추출 """
    similarity_list = [{'similarity': -1.0}, {'similarity': -1.0}, {'similarity': -1.0}]
    for doc, score in zip(data, dot_score_list):
        doc['similarity'] = score
        sim_list = [d['similarity'] for d in similarity_list]
        if score > min(sim_list):
            idx_min = sim_list.index(min(sim_list))
            similarity_list[idx_min] = doc

    """ 3. 유사도 점수가 기준 점수(SIMILARITY_CRITERION_POINT) 이하인 데이터 삭제 """
    result_similarity_list = []
    for doc in similarity_list:
        if doc['similarity'] > SIMILARITY_CRITERION_POINT:
            result_similarity_list.append(doc)

    # 유사도 상위 3개의 데이터 출력
    # print(result_similarity_list)

    """ 요약된 질문과 답변을 DTO로 담아서 Spring Boot로 전달한다. """
    # List of DTOs
    data_list = []
    for i in result_similarity_list:
        dict_ = dict()
        dict_['question_summary'] = i.get('question_summary')
        dict_['answer'] = i.get('answer')
        data_list.append(dict_)

    return data_list


if __name__ == '__main__':
    app.run(debug=True)
