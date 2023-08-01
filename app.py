from flask import Flask, request, jsonify
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


@app.route('/api/chat/flask', methods=['POST'])
def message_from_spring_boot():
    """ Declare variables """
    mentor_nickname = None
    mentee_nickname = None
    question_origin = None
    question_summary = None  # 한글 세줄 요약본

    try:
        """ Get data from Spring Boot Server """
        data = request.get_json()
        mentor_nickname = data['mentor_nickname']
        mentee_nickname = data['mentee_nickname']
        question_origin = data['question_origin']
        question_summary = data['question_summary']

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    """ Use AWS Translate to translate the text """
    translation_response = translate.translate_text(Text=question_summary, SourceLanguageCode=SOURCE_LANGUAGE_CODE,
                                                    TargetLanguageCode=TARGET_LANGUAGE_CODE)

    # Extract the translated text from the response: 영어 세줄 요약본
    translated_text = translation_response['TranslatedText']

    """ Connect to MongoDB using PyMongo """
    mongo_client = get_mongo_client()
    menjil_db = mongo_client['menjil']
    qa_collection = menjil_db['qa_list']

    # Get documents from a collection
    # Filter when mentor_nickname exists and answer is not null
    filter_query = {'mentor_nickname': mentor_nickname, 'answer': {'$exists': True, '$ne': None}}
    data = []

    for document in qa_collection.find(filter_query):
        data.append(document)

    print(data)

    if len(data) < 3:
        # 데이터가 충분하지 않아서 유사도가 높은 문답 목록을 제공하지 못한다는 메시지를 보낸다.
        print("hi")

    """문장 유사도 검증"""
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    # 기존의 질문을 mongodb에 저장하고, 답변이 올 때까지 기다린다. 답변 오면 update 처리 <- 이건 스프링 부트에서.

    return jsonify({'error': 'ho'})


if __name__ == '__main__':
    app.run()
