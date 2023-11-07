import re

def extract_syns(text):
    regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
    matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
    if matches:
        # [('M. recutita L.', '[syn. M. recutita L.]')]
        return [(x[3], x[0]) for x in matches]
    return []



print(extract_syns('Scherb. (syn. Senecio paludosus L.) – Rodopi'))
print(extract_syns('Scherb. [syn. Senecio paludosus L.] – Rodopi'))
print(extract_syns('Scherb. (Syn. Senecio paludosus L.) – Rodopi'))
print(extract_syns('Scherb. [Syn. Senecio paludosus L.] – Rodopi'))
print(extract_syns('Scherb. (syn.: Senecio paludosus L.) – Rodopi'))
