import re

a='.... ? huuuuuh'


print(re.sub(r'([^A-Za-z0-9])\1{3,}', r'\1', a))
