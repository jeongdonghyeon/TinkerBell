import boto3

# 우리가 사용할 컬렉션 ID와 등록할 이미지 파일 이름
COLLECTION_ID = 'family_faces'
IMAGE_FILE = '../Fonts/family.jpg'

# boto3 rekognition 클라이언트 생성
rekognition_client = boto3.client('rekognition', region_name='ap-northeast-2')

def create_collection(collection_id):
    """
    컬렉션을 생성하는 함수
    """
    try:
        rekognition_client.create_collection(CollectionId=collection_id)
        print(f"컬렉션 '{collection_id}'를 생성했습니다.")
    except rekognition_client.exceptions.ResourceAlreadyExistsException:
        print(f"컬렉션 '{collection_id}'가 이미 존재합니다.")
    except Exception as e:
        print(f"컬렉션 확인 중 오류 발생: {e}")

def index_face(collection_id, image_file):
    """
    지정된 이미지 파일의 얼굴을 컬렉션에 등록(인덱싱)합니다.
    """
    try:
        # 이미지 파일을 바이너리(binary) 모드로 읽습니다.
        with open(image_file, 'rb') as f:
            image_bytes = f.read()

        # index_faces API 호출
        response = rekognition_client.index_faces(
            CollectionId=collection_id,
            Image={'Bytes': image_bytes},
            ExternalImageId=image_file, # 사진 파일 이름을 식별자로 사용
            DetectionAttributes=['DEFAULT']
        )

        # 응답 결과 확인
        if response['FaceRecords']:
            face_id = response['FaceRecords'][0]['Face']['FaceId']
            print(f"'{image_file}'의 얼굴을 성공적으로 등록했습니다.")
            print(f"  - Face ID: {face_id}")
        else:
            print(f"'{image_file}'에서 얼굴을 찾지 못했습니다.")

    except FileNotFoundError:
        print(f"오류: 이미지 파일 '{image_file}'을 찾을 수 없습니다. 프로젝트 폴더에 저장했는지 확인하세요.")
    except Exception as e:
        print(f"얼굴 등록 중 오류 발생: {e}")


if __name__ == '__main__':
    # 1. 컬렉션이 있는지 확인하고 없으면 생성합니다.
    create_collection(COLLECTION_ID)

    # 2. 지정된 이미지의 얼굴을 컬렉션에 등록합니다.
    index_face(COLLECTION_ID, IMAGE_FILE)