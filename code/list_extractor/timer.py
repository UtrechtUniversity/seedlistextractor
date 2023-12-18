import time

class Timer:

    # self.timer=Timer()
    # self.timer.start()

    # self.timer.checkpoint(label='label')
    # pprint(self.timer.get_checkpoints(), width=100, sort_dicts=False)

    # n=self.timer.average(label='link #1')
    # self.timer.average(label='link #1', key=n)
    # pprint(self.timer.get_averages(label='link #4'), width=100, sort_dicts=False)

    checkpoints=[]
    averages=[]

    def __init__(self):
        self.start_time=None

    def start(self):
        self.start_time=time.perf_counter()

    def checkpoint(self, label):
        self.checkpoints.append({'key': len(self.checkpoints), 'label': label, 'start_time': time.perf_counter()})

    def get_checkpoints(self, sort_by_length=True):
        start=self.start_time
        for item in (self.checkpoints):
            item.update({'took': item['start_time']-start})
            start=item['start_time']
            del item['start_time']

        if sort_by_length:
            self.checkpoints=sorted(self.checkpoints, key=lambda x: -x['took'])
        
        return self.checkpoints
    
    def average(self, label, key=None):
        if key is None:
            key=len(self.averages)
            self.averages.append({'key': key, 'label': label, 'start_time': time.perf_counter()})
            return key
        else:
            item=[x for x in self.averages if x['key']==key]
            if len(item)>0:
                item[0].update({'end_time': time.perf_counter()})

    def get_averages(self, label):
        tot=0
        items=[x for x in self.averages if x['label']==label]
        for item in items:
            tot += item['end_time']-item['start_time']
        return {'label': label, 'avg': tot/len(items), 'tot': tot, 'tot_len': len(items)}

