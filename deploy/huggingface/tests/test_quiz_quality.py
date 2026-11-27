"""Adversarial checks for fact diversity and bounded recovery; no model download."""
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'deploy/huggingface/gradio-quiz'))
sys.path.insert(0,str(ROOT/'AI Chat'))
from app.engine import ChatFailure
from grounded_quiz import evidence_passages, validate_indexed_question
from quiz_quality import CandidateFailure, DiversityGuard, evidence_order, facet, question_guidance, questions_equivalent
from quiz_set import generate_quiz_set

NAME='Bình gốm DEMO'
FACTS=[
 ('Bình gốm được dùng để đựng nước.','Bình gốm dùng để làm gì?',['Đựng nước','Dệt vải','Ghi chép','Nấu cơm']),
 ('Chất liệu là đất nung.','Bình gốm được làm bằng chất liệu gì?',['Đất nung','Sắt','Nhựa','Thủy tinh']),
 ('Miệng bình loe rộng.','Miệng bình có đặc điểm gì?',['Loe rộng','Thu hẹp','Thẳng đứng','Khép kín']),
 ('Thân bình có hoa văn khắc chìm.','Thân bình có loại hoa văn gì?',['Khắc chìm','In nổi','Dát vàng','Không trang trí']),
 ('Bình được làm bằng kỹ thuật bàn xoay.','Bình được làm bằng kỹ thuật gì?',['Bàn xoay','Đúc khuôn','Thổi thủy tinh','In máy']),
]
SOURCE=' '.join(item[0] for item in FACTS)


def draft(question,answer,quote):
    return {'question':question,'options':[answer,'Khác một','Khác hai','Khác ba'],'correctIndex':0,
        'explanation':quote,'evidenceQuote':quote}


class ScriptedEngine:
    def __init__(self, bad_first=False, all_bad=False, quota_after=None):
        self.lock=threading.Lock()
        self.calls=[]
        self.bad_first,self.all_bad,self.quota_after=bad_first,all_bad,quota_after

    def generate_json(self,prompt,validator,**kwargs):
        payload=json.loads(prompt.rsplit('<|im_start|>user\n',1)[1].split('<|im_end|>')[0])
        self.calls.append((payload,kwargs))
        if self.quota_after is not None and len(payload['EXCLUDED'])>=self.quota_after:
            raise ChatFailure('Quota hết.',503)
        if self.all_bad or (self.bad_first and payload['TARGET_EVIDENCE']['id']==0):
            raise CandidateFailure('grounding','Chọn lại đáp án từ đoạn mục tiêu.')
        quote=payload['TARGET_EVIDENCE']['text']
        match=next(row for row in FACTS if row[0]==quote)
        candidate={'question':match[1]} if payload.get('QUESTION_ONLY') else {'question':match[1],'options':match[2],'correctIndex':0}
        return validator(json.dumps(candidate,ensure_ascii=False))


class QualityTests(unittest.TestCase):
    def test_actual_failed_pair_is_a_paraphrase(self):
        self.assertTrue(questions_equivalent('Bình gốm DEMO được làm bằng cách nào?',
            'Bình gốm này được làm bằng cách nào?',NAME))

    def test_same_fact_with_different_quote_and_question_is_rejected(self):
        guard=DiversityGuard(NAME,[])
        guard.accept(draft('Bình gốm được làm bằng cách nào?','Bàn xoay',FACTS[4][0]))
        with self.assertRaises(CandidateFailure):
            guard.accept(draft('Phương pháp người thợ dùng là gì?','Kỹ thuật bàn xoay',
                'Người thợ dùng phương pháp bàn xoay để tạo bình.'))

    def test_distinct_shape_facts_remain_usable(self):
        guard=DiversityGuard(NAME,[])
        guard.accept(draft('Miệng bình có hình dạng gì?','Loe rộng',FACTS[2][0]))
        guard.accept(draft('Thân bình có hình dạng gì?','Hình trụ','Thân bình có hình trụ.'))
        self.assertEqual(len(guard.accepted),2)

    def test_source_answer_alone_does_not_make_wrong_topic_acceptable(self):
        with self.assertRaises(CandidateFailure) as error:
            DiversityGuard(NAME,[]).accept(draft('Bình được làm bằng cách nào?','Đựng nước',FACTS[0][0]))
        self.assertEqual(error.exception.code,'wrong_topic')

    def test_negative_question_is_not_accepted_as_positive_fact(self):
        with self.assertRaises(CandidateFailure):
            DiversityGuard(NAME,[]).accept(draft('Công dụng nào không đúng với bình?','Đựng nước',FACTS[0][0]))

    def test_actual_cpu_language_drift_is_rejected(self):
        with self.assertRaises(CandidateFailure) as error:
            DiversityGuard(NAME,[]).accept(draft('Bình gốm này được dùng để干嘛?','Đựng nước',FACTS[0][0]))
        self.assertEqual(error.exception.code,'language')

    def test_actual_cpu_english_and_nonsense_distractors_are_rejected(self):
        text=json.dumps({'question':'Chất liệu của bình là gì?',
            'options':['Đất nung','Ceramic','Nước','Sap chiên'],'correctIndex':0})
        with self.assertRaises(CandidateFailure):
            validate_indexed_question(text,FACTS[1][0],[FACTS[1][0]],0,[])

    def test_english_question_is_rejected_even_if_answer_is_vietnamese(self):
        with self.assertRaises(CandidateFailure):
            DiversityGuard(NAME,[]).accept(draft('What is this vase used for?','Đựng nước',FACTS[0][0]))

    def test_yes_no_question_with_source_grounded_options_is_rejected(self):
        with self.assertRaises(CandidateFailure) as error:
            DiversityGuard(NAME,[]).accept(draft('Miệng bình rộng không?','Loe rộng',FACTS[2][0]))
        self.assertEqual(error.exception.code,'yes_no_question')

    def test_yes_no_response_is_not_an_extractive_answer(self):
        text=json.dumps({'question':'Miệng bình rộng không?','options':['Có','Không','Rất rộng','Rất nhỏ'],'correctIndex':0})
        with self.assertRaises(CandidateFailure):
            validate_indexed_question(text,FACTS[2][0],[FACTS[2][0]],0,[])

    def test_legacy_exclusion_paraphrase_is_rejected(self):
        guard=DiversityGuard(NAME,['Bình gốm DEMO được làm bằng cách nào?'])
        with self.assertRaises(CandidateFailure):
            guard.accept(draft('Bình gốm này được làm bằng cách nào?','Bàn xoay',FACTS[4][0]))

    def test_clauses_are_original_substrings_and_metadata_is_not_a_fact(self):
        source='Chất liệu là đất nung, miệng bình loe rộng và thân bình có hoa văn khắc chìm. Bình được làm bằng kỹ thuật bàn xoay; bình được dùng để đựng nước. Đây là tư liệu giả lập để kiểm thử phần mềm.'
        parts=evidence_passages(source)
        self.assertEqual(len(parts),5)
        self.assertTrue(all(part in source for part in parts))

    def test_decimals_are_not_split_into_fake_facts(self):
        self.assertEqual(evidence_passages('Chiều cao của bình là 12,5 cm.'),['Chiều cao của bình là 12,5 cm.'])

    def test_material_answer_can_come_from_natural_source_wording(self):
        self.assertEqual(question_guidance(NAME,'Bình được làm từ gỗ.')['answer'],'gỗ')

    def test_made_since_a_year_is_not_misread_as_a_material(self):
        self.assertEqual(facet('Bình được làm từ năm 1840.'),'date')

    def test_metadata_alone_is_not_a_quiz_source(self):
        with self.assertRaises(ChatFailure):
            evidence_passages('Đây là tư liệu giả lập để kiểm thử phần mềm.')

    def test_fact_planner_prefers_distinct_topics_over_repeated_materials(self):
        parts=evidence_passages('Chất liệu là đất nung. Vật liệu làm từ đất nung. '+SOURCE)
        order=evidence_order(parts,NAME,[])
        self.assertEqual(len(order),5)
        self.assertEqual(len({facet(parts[i],NAME) for i in order[:5]}),5)

    def test_other_source_fact_can_be_a_distractor(self):
        text=json.dumps({'question':'Chất liệu của bình là gì?','options':['Đất nung','Đồng','Nhựa','Gỗ'],'correctIndex':0})
        result,_=validate_indexed_question(text,'Chất liệu là đất nung. Chuông được đúc bằng đồng.',
            ['Chất liệu là đất nung.','Chuông được đúc bằng đồng.'],0,[])
        self.assertEqual(result['options'][result['correctIndex']],'Đất nung')

    def test_generation_scans_next_fact_after_two_invalid_candidates(self):
        engine=ScriptedEngine(bad_first=True)
        result=generate_quiz_set(engine,NAME,SOURCE,'easy',[],3)
        self.assertTrue(result['complete'])
        self.assertEqual(result['generatedCount'],3)
        self.assertNotIn(FACTS[0][0],[q['evidenceQuote'] for q in result['questions']])
        self.assertTrue(engine.calls[1][0]['CORRECTION'])
        self.assertEqual([engine.calls[i][1]['temperature'] for i in (0,1)],[0.0,.35])

    def test_five_questions_cover_five_facts(self):
        result=generate_quiz_set(ScriptedEngine(),NAME,SOURCE,'easy',[],5)
        self.assertTrue(result['complete'])
        self.assertEqual(result['distinctEvidenceCount'],5)
        self.assertTrue(result['reviewRequired'])
        for item in result['questions']:
            self.assertEqual(len(item['options']),4)
            self.assertEqual(len(set(item['options'])),4)
            self.assertIn(item['options'][item['correctIndex']].casefold(),item['evidenceQuote'].casefold())

    def test_historical_prose_supplies_five_different_grounded_targets(self):
        source = """Trong thế kỷ XV–XVI, nghề sản xuất gốm tại Đại Việt phát triển mạnh mẽ, đặc biệt là dòng gốm hoa lam. Các sản phẩm gốm không chỉ phục vụ nhu cầu sinh hoạt trong nước mà còn trở thành mặt hàng xuất khẩu thông qua những tuyến thương mại hàng hải quốc tế.

Bên cạnh các loại bát, đĩa và bình truyền thống, những người thợ gốm còn sáng tạo các vật dụng mang hình dáng động vật và linh vật, trong đó có ấm hình chim phượng.

Những hiện vật cùng loại được tìm thấy trong tàu cổ Cù Lao Chàm là minh chứng cho sự phát triển của nghề gốm và vai trò của Đại Việt trong hoạt động giao thương quốc tế vào cuối thế kỷ XV.

Ngày nay, những chiếc ấm gốm hình chim phượng mang giá trị lịch sử, văn hóa và nghệ thuật, góp phần giới thiệu di sản gốm truyền thống Việt Nam đến công chúng trong nước và quốc tế."""
        class HintEngine(ScriptedEngine):
            def generate_json(self, prompt, validator, **kwargs):
                payload = json.loads(prompt.rsplit('<|im_start|>user\n',1)[1].split('<|im_end|>')[0])
                return validator(json.dumps({'question': payload['QUESTION_HINT']}))
        result = generate_quiz_set(HintEngine(), 'Ấm gốm hoa lam hình chim phượng', source, 'medium', [], 5)
        self.assertTrue(result['complete'])
        self.assertEqual(result['distinctEvidenceCount'], 5)
        answers = {q['options'][q['correctIndex']].casefold() for q in result['questions']}
        self.assertEqual(answers, {'gốm hoa lam', 'tuyến thương mại hàng hải quốc tế', 'chim phượng',
                                   'tàu cổ cù lao chàm', 'công chúng trong nước và quốc tế'})

    def test_no_server_question_is_filled_when_model_returns_empty_json(self):
        class EmptyModel(ScriptedEngine):
            def generate_json(self,prompt,validator,**kwargs):
                return validator('{}')
        with self.assertRaises(CandidateFailure) as error:
            generate_quiz_set(EmptyModel(),NAME,SOURCE,'easy',[],5)
        self.assertEqual(error.exception.code,'question_schema')

    def test_model_cannot_inject_uncontrolled_options_in_question_only_mode(self):
        class ExtraOptions(ScriptedEngine):
            def generate_json(self,prompt,validator,**kwargs):
                return validator(json.dumps({'question':'Bình gốm dùng để làm gì?',
                    'options':['Câu bịa'],'correctIndex':0}))
        with self.assertRaises(CandidateFailure) as error:
            generate_quiz_set(ExtraOptions(),NAME,SOURCE,'easy',[],5)
        self.assertEqual(error.exception.code,'question_schema')

    def test_insufficient_source_does_not_pad_to_five(self):
        result=generate_quiz_set(ScriptedEngine(),NAME,FACTS[0][0],'easy',[],5)
        self.assertFalse(result['complete'])
        self.assertEqual(result['generatedCount'],1)

    def test_quota_keeps_valid_questions_but_stops_generation(self):
        engine=ScriptedEngine(quota_after=2)
        result=generate_quiz_set(engine,NAME,SOURCE,'easy',[],5)
        self.assertFalse(result['complete'])
        self.assertEqual(result['generatedCount'],2)
        self.assertEqual(len(engine.calls),3)

    def test_retry_attempts_are_bounded_when_every_candidate_is_invalid(self):
        engine=ScriptedEngine(all_bad=True)
        with self.assertRaises(ChatFailure):
            generate_quiz_set(engine,NAME,SOURCE,'easy',[],5)
        self.assertLessEqual(len(engine.calls),15)

    def test_zero_budget_does_not_call_model(self):
        engine=ScriptedEngine()
        with self.assertRaises(ChatFailure) as error:
            generate_quiz_set(engine,NAME,SOURCE,'easy',[],5,budget_seconds=0)
        self.assertEqual(error.exception.status,504)
        self.assertEqual(len(engine.calls),0)


if __name__=='__main__':
    unittest.main()
