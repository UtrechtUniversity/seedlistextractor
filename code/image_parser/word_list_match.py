from fastDamerauLevenshtein import damerauLevenshtein
           
class WordListMatch:

    def __init__(self, db_conn, word_list_path) -> None:
        self.conn=db_conn
        self.words=[]

        with open(word_list_path) as f:
            words=[x.strip() for x in list(map(lambda x: x.lower(),f.read().splitlines())) if len(x.strip())>2]

        cur=self.conn.cursor()
        for word in words:
            cword="".join([x for x in word if x.isalnum()])
            query=(f"select count(*) as total \
                   from name_lookup \
                   where epithet match '{cword}' \
                   or genus match '{cword}' \
                   or family match '{cword}' \
                   or subfamily match '{cword}' \
                   or tribe match '{cword}' \
                   or subtribe match '{cword}' ")
            cur.execute(query)
            row=cur.fetchone()
            if int(row[0])>0:
                self.words.append(word)

    def get_matches(self, word, top=5):
        candidates=[(x, damerauLevenshtein(word.lower(), x)) for x in self.words]
        candidates=sorted(candidates, key=lambda x: -x[1])
        candidates=candidates[:top]
        return candidates



    # def set_word_list_matcher(self, path):
    #     if not self.config['use_word_list']:
    #         return

    #     word_list_path=path / Path('wordlist.txt')
    #     if not word_list_path.exists():
    #         return
    #     self.word_list_matcher=WordListMatch(
    #         db_conn=self.conn, 
    #         word_list_path=word_list_path)

    # def get_word_list_match(self, word):
    #     if self.word_list_matcher:
    #         self.word_list_matcher.get_matches(word=word, top=3)