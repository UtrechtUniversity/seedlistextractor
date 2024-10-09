class NameListChecks:

    def __init__(self, lines):
        self.lines = lines
    
    def run(self):
        self.genera_alphabetical_order()

        # print(self.lines)

        return self.lines

    def genera_alphabetical_order(self):

        def get_genus(line):
            if line.name:
                return line.name.match.genus
            elif line.genus:
                return line.genus.match.genus

        err = []

        for line in self.lines:
            genus = get_genus(line)
            if not genus:
                continue
            
            p = [x for x in self.lines if x.line_nr<line.line_nr and (x.name or x.genus) and x.line_nr not in err]
            p = p.pop() if len(p)>0 else None
            n = next((x for x in self.lines if x.line_nr>line.line_nr and (x.name or x.genus)), None)

            p_genus = get_genus(p) if p else None
            n_genus = get_genus(n) if n else None

            a = '.'
            if not ((p_genus is None or genus>=p_genus) and (n_genus is None or genus<=n_genus)):
                a = 'x'
                err.append(line.line_nr)

            # print(f"{a} {genus}")

        err2 = []
        for line in self.lines:
            genus = get_genus(line)
            if not genus:
                continue
            
            p = [x for x in self.lines if x.line_nr<line.line_nr and (x.name or x.genus) and x.line_nr not in err]
            p = p.pop() if len(p)>0 else None
            n = next((x for x in self.lines if x.line_nr>line.line_nr and (x.name or x.genus) and x.line_nr not in err), None)

            p_genus = get_genus(p) if p else None
            n_genus = get_genus(n) if n else None

            a = '.'
            if not ((p_genus is None or genus>=p_genus) and (n_genus is None or genus<=n_genus)):
                err2.append(line.line_nr)
                a = 'X'

                # errors = line.errors
                # errors.append('genus alphabetical mismatch')
                # setattr(line, 'errors', errors)

            print(f"{a} {genus}")

        # print(err2)
        # exit()

