import json, re

def parse_json_object(text: str):
    text=(text or '').strip()
    if not text:
        raise ValueError('Empty model response')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m=re.search(r'```(?:json)?\s*(.*?)```', text, re.S|re.I)
        if m:
            return json.loads(m.group(1).strip())
        start=min([i for i in (text.find('{'), text.find('[')) if i >= 0], default=-1)
        if start < 0:
            raise
        opener=text[start]
        closer='}' if opener=='{' else ']'
        end=text.rfind(closer)
        if end < start:
            raise
        return json.loads(text[start:end+1])
