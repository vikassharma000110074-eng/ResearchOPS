import json, shutil, subprocess, tempfile
from pathlib import Path
from collections import defaultdict
from researchops_backend.core.config import get_settings

class HadoopStreamingEngine:
    name='hadoop-streaming'
    def __init__(self):
        self.s=get_settings()
        if not shutil.which(self.s.hadoop_binary): raise RuntimeError('Hadoop binary not found')
        if not self.s.hadoop_streaming_jar: raise RuntimeError('HADOOP_STREAMING_JAR is not configured')

    @classmethod
    def available(cls):
        s=get_settings()
        return bool(shutil.which(s.hadoop_binary) and s.hadoop_streaming_jar and Path(s.hadoop_streaming_jar).exists())

    def _run(self,*args, capture=False):
        return subprocess.run([self.s.hadoop_binary,*args], check=True, text=True, capture_output=capture)

    def run(self, documents, research_id=None):
        research_id=research_id or 'adhoc'; base=f'/researchops/{research_id}'
        input_dir=f'{base}/input'; output_dir=f'{base}/output'
        mapper=Path(__file__).with_name('mapper.py'); reducer=Path(__file__).with_name('reducer.py')
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)/'documents.jsonl'
            local.write_text('\n'.join(json.dumps(d,ensure_ascii=False) for d in documents), encoding='utf-8')
            subprocess.run([self.s.hadoop_binary,'fs','-rm','-r','-f',base], check=False, capture_output=True, text=True)
            self._run('fs','-mkdir','-p',input_dir)
            self._run('fs','-put','-f',str(local),f'{input_dir}/documents.jsonl')
            cmd=[self.s.hadoop_binary,'jar',self.s.hadoop_streaming_jar,
                 '-D','mapreduce.job.name=ResearchOpsMapReduce',
                 '-files',f'{mapper},{reducer}',
                 '-input',input_dir,'-output',output_dir,
                 '-mapper','python3 mapper.py','-reducer','python3 reducer.py']
            subprocess.run(cmd,check=True,text=True)
            out=self._run('fs','-cat',f'{output_dir}/part-*',capture=True).stdout
        topics=defaultdict(lambda:{'documents':0,'tokens':0,'risk_terms':0,'opportunity_terms':0,'terms':{},'domains':{}})
        for line in out.splitlines():
            try: key,val=line.split('\t',1); topic,metric=key.split('|',1); val=int(val)
            except Exception: continue
            t=topics[topic]
            if metric=='__documents__': t['documents']=val
            elif metric=='__tokens__': t['tokens']=val
            elif metric=='__risk_terms__': t['risk_terms']=val
            elif metric=='__opportunity_terms__': t['opportunity_terms']=val
            elif metric.startswith('term:'): t['terms'][metric[5:]]=val
            elif metric.startswith('domain:'): t['domains'][metric[7:]]=val
        for t in topics.values():
            t['top_terms']=sorted(t.pop('terms').items(),key=lambda x:x[1],reverse=True)[:20]
            t['top_domains']=sorted(t.pop('domains').items(),key=lambda x:x[1],reverse=True)[:12]
        return dict(topics)
