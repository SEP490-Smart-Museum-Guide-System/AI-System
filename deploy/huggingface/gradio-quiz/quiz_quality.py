"""Lightweight Vietnamese diversity checks, not an independent semantic verifier."""
import re
import unicodedata
from app.engine import ChatFailure
from app.studio import norm


class CandidateFailure(ChatFailure):
    def __init__(self, code, message):
        super().__init__(message, 502)
        self.code = code


FACETS = (
    ('height', r'chiều cao|độ cao|cao bao nhiêu'),
    ('width', r'chiều rộng|đường kính|rộng bao nhiêu'),
    ('weight', r'khối lượng|trọng lượng|nặng bao nhiêu'),
    ('date', r'niên đại|thế kỷ|thời kỳ|thuộc thời|từ năm|vào năm|năm nào|khi nào|năm\s+\d{3,4}'),
    ('decoration', r'hoa văn|họa tiết|trang trí|khắc chìm|khắc nổi'),
    ('material', r'chất liệu|vật liệu|làm từ|làm bằng gì|chế tác từ'),
    ('technique', r'kỹ thuật|phương pháp|bàn xoay|bằng cách nào|cách làm|quy trình'),
    ('purpose', r'công dụng|mục đích|dùng để|được dùng|dùng làm|sử dụng để|sử dụng vào|để làm gì'),
    ('origin', r'xuất xứ|nguồn gốc|sản xuất tại|chế tác tại|đến từ|vùng nào'),
    ('location', r'trưng bày tại|lưu giữ tại|bảo quản tại|đang ở đâu'),
    ('shape', r'hình dáng|hình dạng|miệng|thân|đáy|loe rộng|dáng tròn'),
)
STOP = set('la co duoc cua va nay do cac mot nhung hien vat nao gi nhu the bao nhieu de lam bang tu su dung viec khi thi ve voi ky thuat phuong phap chat lieu vat cong muc dich che tac tao loai cach hinh dang'.split())
META = re.compile(r'^(?:đây là\s+)?(?:tư liệu giả lập|dữ liệu kiểm thử)|^không phải hồ sơ hiện vật thật|^lưu ý.*kiểm thử', re.I)
FOREIGN_WORDS = {'ceramic','metal','plastic','wood','water','yes','no','none'}


def folded(text):
    text = norm(text).replace('chứa', 'đựng').replace('đ', 'd')
    return ''.join(char for char in unicodedata.normalize('NFD', text) if not unicodedata.combining(char))


def without_name(text, name):
    value = norm(text)
    return value.replace(norm(name), ' ') if name.strip() else value


def facet(text, name=''):
    value = without_name(text, name)
    return next((label for label, pattern in FACETS if re.search(pattern, value)), None)


def signature(text, name='', *, include_facet=True):
    topic = facet(text, name)
    words = set(re.findall(r'[a-z0-9]+', folded(text)))
    words -= STOP | set(re.findall(r'[a-z0-9]+', folded(name)))
    if include_facet and topic:
        words.add('facet_' + topic)
    return words


def similar(left, right):
    if not left or not right:
        return False
    return left == right or len(left & right) / len(left | right) >= .85


def questions_equivalent(left, right, name):
    return norm(left) == norm(right) or similar(signature(left, name), signature(right, name))


# Keep the whole historical sentence as evidence. Splitting a sentence at a
# comma can detach the subject from its period, trading route or findspot.
CAPITALIZED_WORD = r'[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][^\W\d_]*'
HISTORICAL_FACTS = (
    ('findspot', r'(?:tìm thấy|phát hiện)\s+(?:được\s+)?(?:trong|tại|ở)\s+'
     rf'((?:tàu cổ|tàu đắm|di chỉ|di tích|hang động)\s+(?-i:{CAPITALIZED_WORD}(?:[ -]{CAPITALIZED_WORD})*))',
     'Những hiện vật được nhắc đến trong tư liệu đã được tìm thấy ở đâu?',
     ('Thành nhà Hồ', 'Di chỉ Đồng Đậu', 'Hang Con Moong', 'Di tích Óc Eo')),
    ('trade_route', r'(?:thông qua|theo|qua)\s+(?:những |các )?'
     r'((?:tuyến (?:thương mại |giao thương )?)?(?:hàng hải|đường biển)(?: quốc tế)?)\b',
     'Sản phẩm trong tư liệu được trao đổi qua tuyến giao thương nào?',
     ('Tuyến đường bộ qua núi', 'Tuyến đường sông nội địa', 'Tuyến đường sắt', 'Tuyến hàng không')),
    ('motif', r'\b(?:ấm|bình|tượng|đèn|lọ|bát)\s+(?:có )?(?:hình|dáng)\s+'
     r'(chim phượng|phượng hoàng|chim uyên ương|uyên ương|sư tử|cá chép|rồng|voi|rùa|hổ)\b',
     'Con vật nào được dùng làm hình mẫu cho vật dụng trong tư liệu?',
     ('Cá chép', 'Hươu', 'Rùa', 'Voi', 'Hổ', 'Ngựa')),
    ('audience', r'\b(?:đến|tới|cho)\s+((?:công chúng|khách tham quan|du khách)\s+'
     r'(?:trong nước và quốc tế|quốc tế và trong nước|địa phương|quốc tế|trong nước))\b',
     'Tư liệu nhắc đến những ai là đối tượng được giới thiệu di sản?',
     ('Riêng hội đồng thẩm định', 'Chỉ các thợ phục chế', 'Riêng đoàn khảo cổ', 'Chỉ các nhà sưu tập')),
    ('ceramic_type', r'\b(?:dòng|loại)\s+(gốm (?:hoa lam|men ngọc|hoa nâu|men trắng|men nâu|men rạn))\b',
     'Dòng gốm nào được nhấn mạnh trong tư liệu?',
     ('Gốm men ngọc', 'Gốm hoa nâu', 'Gốm men rạn', 'Gốm men trắng', 'Gốm men đen')),
)


def historical_guidance(quote):
    for topic, pattern, question, alternatives in HISTORICAL_FACTS:
        match = re.search(pattern, quote, re.I)
        if match:
            answer = match.group(1)
            pool = [value for value in alternatives if norm(value) not in norm(quote)]
            if len(pool) >= 3:
                return {'topic': topic, 'question': question, 'answer': answer, 'distractors': pool}
    return None


HISTORICAL_QUESTIONS = (
    ('findspot', r'ở đâu|tại đâu|địa điểm nào|nơi nào|tàu (?:cổ|đắm) nào'),
    ('trade_route', r'(?:tuyến|con đường|đường|hình thức vận chuyển)[^?]{0,35} nào'),
    ('motif', r'(?:con vật|loài|linh vật|động vật|hình tượng) nào|hình (?:con |loài )?gì'),
    ('audience', r'công chúng nào|những ai|đối tượng nào|đến ai|tới ai|cho ai'),
    ('ceramic_type', r'(?:dòng|loại) gốm (?:nào|gì)'),
)


def question_guidance(name, quote):
    historical = historical_guidance(quote)
    if historical:
        return historical
    topic = facet(quote, name)
    stems = {
        'purpose':f'Theo tư liệu, {name} được dùng để làm gì?',
        'material':f'Theo tư liệu, {name} được làm từ chất liệu gì?',
        'technique':f'Theo tư liệu, {name} được chế tác bằng kỹ thuật gì?',
        'decoration':f'Theo tư liệu, {name} có họa tiết hoặc cách trang trí nào?',
        'shape':f'Theo tư liệu, hình dáng của {name} có đặc điểm gì?',
    }
    if topic == 'shape' and norm(quote).startswith('miệng'):
        stems['shape']=f'Theo tư liệu, miệng của {name} có đặc điểm gì?'
    patterns = {
        'purpose':r'(?:dùng|sử dụng) (?:để|làm)\s+(.+?)[.!?]*$',
        'material':r'(?:(?:chất liệu|vật liệu)\s*(?:là|:)|(?:làm|chế tác)\s+(?:từ|bằng))\s*(.+?)[.!?]*$',
        'technique':r'(?:kỹ thuật|phương pháp)\s+(.+?)[.!?]*$',
        'decoration':r'(?:hoa văn|họa tiết)\s+(.+?)[.!?]*$',
        'shape':r'\b(loe rộng|hình trụ|hình cầu|hình hộp|hình nón|dáng tròn)\b',
    }
    match=re.search(patterns.get(topic,r'(?!)'),quote,re.I)
    answer=match.group(1).strip().rstrip('.!?') if match else None
    pools = {
        'purpose':['Nấu cơm','Dệt vải','Ghi chép','Thắp sáng','Đựng thóc'],
        'material':['Gỗ','Đồng','Sắt','Nhựa','Thủy tinh','Đá'],
        'technique':['Đúc khuôn','Nặn tay','Chạm khắc','Rèn thủ công','Thổi thủy tinh','In máy'],
        'decoration':['Khắc nổi','In nổi','Đắp nổi','Dát vàng','Không trang trí'] if answer and 'khắc' in norm(answer)
            else ['Hình chim','Hình lá','Cánh sen','Sóng nước','Hình mặt trăng'],
        'shape':['Thu hẹp','Thẳng đứng','Khép kín','Bịt kín','Hình vuông'] if answer and 'loe' in norm(answer)
            else ['Hình cầu','Hình hộp','Hình nón','Hình trụ','Hình chóp'],
    }
    pool=[value for value in pools.get(topic,[]) if norm(value) not in norm(quote)
        and (not answer or norm(value)!=norm(answer))]
    return {'topic':topic,'question':stems.get(topic),'answer':answer,'distractors':pool if len(pool)>=3 else []}


def validate_language(candidate, source, name):
    if re.search(r'^(?:what|which|where|how|when|why|is|are|does|do)\b',without_name(candidate['question'],name)):
        raise CandidateFailure('language','Câu hỏi phải viết bằng tiếng Việt, không dùng câu hỏi tiếng Anh.')
    for text in [candidate['question'],*candidate['options']]:
        if any(char.isalpha() and 'LATIN' not in unicodedata.name(char,'') and char not in source+name for char in text):
            raise CandidateFailure('language','Chỉ viết tiếng Việt; không chèn chữ Trung Quốc hoặc ký tự ngôn ngữ khác không có trong nguồn.')
        words=set(re.findall(r'[a-z]+',folded(text)))
        if any(word in words and word not in folded(source+' '+name).split() for word in FOREIGN_WORDS):
            raise CandidateFailure('language','Viết câu hỏi và lựa chọn bằng tiếng Việt, không dịch lựa chọn sang tiếng Anh.')


def split_passages(source):
    chunks = []
    for sentence in re.split(r'(?<=[.!?。！？])\s+|\n+|;\s*', source):
        sentence = sentence.strip()
        sentence = re.sub(r'^(?:[-•*]\s+|\d{1,2}[.)]\s+)', '', sentence)
        if not sentence or META.search(sentence):
            continue
        clauses = re.split(r'(?<!\d),(?!\d)\s*|\s+và\s+', sentence)
        pieces = clauses if not historical_guidance(sentence) and sum(facet(part) is not None for part in clauses) >= 2 else [sentence]
        for piece in pieces:
            piece = piece.strip()
            while len(piece) > 1000:
                boundary = piece.rfind(' ', 0, 950)
                boundary = boundary if boundary >= 6 else 950
                part, piece = piece[:boundary].strip(), piece[boundary:].strip()
                if len(part) >= 6:
                    chunks.append(part)
            if len(piece) >= 6:
                chunks.append(piece)
    return list({norm(part): part for part in chunks}.values())


def evidence_order(passages, name, excluded):
    guidance = [question_guidance(name, quote) for quote in passages]
    unique = []
    for index, quote in enumerate(passages):
        topic, tokens = guidance[index]['topic'], signature(quote, name)
        if any(topic == guidance[other]['topic'] and similar(tokens, signature(passages[other], name)) for other in unique):
            continue
        unique.append(index)
    # Prefer different topics first, while retaining the remaining usable facts.
    primary, remaining, topics = [], [], set()
    for index in sorted(unique, key=lambda i: not (guidance[i]['answer'] and guidance[i]['distractors'])):
        topic = guidance[index]['topic']
        if topic is None or topic not in topics:
            primary.append(index)
            if topic: topics.add(topic)
        else:
            remaining.append(index)
    order = primary + remaining
    if order:
        offset = len(excluded) % len(order)
        order = order[offset:] + order[:offset]
    return order


class DiversityGuard:
    def __init__(self, name, excluded):
        self.name, self.excluded, self.accepted = name, list(excluded), []

    def accept(self, candidate):
        question = candidate['question']
        quote = candidate['evidenceQuote']
        answer = candidate['options'][candidate['correctIndex']]
        validate_language(candidate,quote,self.name)
        source_topic = question_guidance(self.name, quote)['topic']
        question_text = without_name(question, self.name)
        question_topic = facet(question, self.name)
        if source_topic in {topic for topic, _ in HISTORICAL_QUESTIONS}:
            question_topic = next((topic for topic, pattern in HISTORICAL_QUESTIONS
                                   if re.search(pattern, question_text)), question_topic)
            if norm(answer) in norm(question):
                raise CandidateFailure('answer_in_question', 'Câu hỏi đã tiết lộ đáp án. Hãy hỏi về dữ kiện mà không nhắc tên đáp án.')
        if re.search(r'không (?:được|phải|dùng|có|là|đúng)|ngoại trừ|khẳng định sai', without_name(question, self.name)):
            raise CandidateFailure('negative_question', 'Hãy hỏi khẳng định, tránh câu phủ định hoặc ngoại trừ.')
        if re.search(r'(?:không|chưa)\s*[?？]?\s*$',norm(question)) or re.search(r'phải chăng|có đúng là|có phải là',norm(question)):
            raise CandidateFailure('yes_no_question','Không hỏi Có/Không; hãy hỏi trực tiếp về công dụng, chất liệu hoặc đặc điểm được giao.')
        if source_topic and question_topic and source_topic != question_topic:
            raise CandidateFailure('wrong_topic', 'Câu hỏi đang hỏi chủ đề khác với dữ kiện được giao; hãy hỏi đúng dữ kiện mục tiêu.')
        if any(questions_equivalent(question, previous, self.name) for previous in self.excluded):
            raise CandidateFailure('duplicate_question', 'Câu hỏi trùng hoặc quá giống câu đã có; cần hỏi một dữ kiện khác.')
        answer_key = signature(answer, include_facet=False)
        for old, old_topic, old_answer in self.accepted:
            if questions_equivalent(question, old['question'], self.name):
                raise CandidateFailure('duplicate_question', 'Câu hỏi chỉ đổi cách diễn đạt của câu đã có.')
            if (source_topic == old_topic or not source_topic or not old_topic) and similar(answer_key, old_answer):
                raise CandidateFailure('duplicate_fact', 'Câu hỏi đang lặp lại cùng đáp án và chủ đề đã khai thác.')
        self.accepted.append((candidate, source_topic, answer_key))
