import asyncio
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('lightrag'),'Official LightRAG environment required')
class OfficialCacheSeparationTests(unittest.TestCase):
    def test_native_cache_honors_separate_online_and_extraction_flags(self):
        from lightrag.utils import handle_cache
        class Store:
            global_config={'enable_llm_cache':False,'enable_llm_cache_for_entity_extract':True}
            reads=0
            async def get_by_id(self,key):
                self.reads+=1
                return {'return':'existing extraction response','create_time':1}
        async def check():
            store=Store()
            query=await handle_cache(store,'hash','prompt',mode='hybrid',cache_type='keywords')
            self.assertIsNone(query)
            self.assertEqual(store.reads,0)
            extraction=await handle_cache(store,'hash','prompt',mode='default',cache_type='extract')
            self.assertEqual(extraction,('existing extraction response',1))
            self.assertEqual(store.reads,1)
        asyncio.run(check())
