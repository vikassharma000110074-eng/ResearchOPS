from concurrent.futures import ThreadPoolExecutor
from researchops_backend.mapreduce.common import map_document, reduce_rows

class LocalMapReduceEngine:
    name='local-mapreduce'
    def __init__(self, workers=6): self.workers=workers
    def run(self, documents, research_id=None):
        rows=[]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for mapped in ex.map(map_document, documents): rows.extend(mapped)
        return reduce_rows(rows)
