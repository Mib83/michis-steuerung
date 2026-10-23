"""Receipt-age guard for the hottest miner channels; no extrapolated samples."""
import math

DEFAULT_FRESHNESS = {'enabled':True,'interval':5.0,'tolerance':2.0,'misses':0}


def validate_freshness(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT_FRESHNESS) or type(value['enabled']) is not bool:
        raise ValueError('Messwertüberwachung unvollständig')
    result={'enabled':value['enabled']}
    for key in ('interval','tolerance','misses'):
        if isinstance(value[key],bool):
            raise ValueError('Zahl erforderlich')
        result[key]=float(value[key])
        if not math.isfinite(result[key]):
            raise ValueError('Endliche Zahl erforderlich')
    if not 1<=result['interval']<=60 or not 0<=result['tolerance']<=30 or result['misses'] not in (0,1,2):
        raise ValueError('Intervall 1–60 s, Toleranz 0–30 s und 0–2 tolerierte Aussetzer wählen')
    result['misses']=int(result['misses'])
    return result


class HottestGuard:
    def __init__(self, config=None):
        self.config=validate_freshness(config or dict(DEFAULT_FRESHNESS))
        self.blocked_since=None
        self.extension=0.0

    def reset(self):
        self.blocked_since=None
        self.extension=0.0

    def snapshot(self,samples,sources,last_sent,pause,now):
        candidates=[]
        for source in sources:
            for i in range(4):
                topic=f"{source['base']}/sm{i}/state"
                sample=samples.get(topic)
                if sample:
                    candidates.append((sample[0],sample[1],topic,source['name']+' · '+source['labels'][i]))
        hottest=max((x[0] for x in candidates),default=None)
        watched=[x for x in candidates if x[0]==hottest]
        oldest=min((x[1] for x in watched),default=None)
        age=max(0,now-oldest) if oldest is not None else None
        limit=self.config['interval']*(self.config['misses']+1)+self.config['tolerance']
        active=self.config['enabled']
        late=bool(active and (age is None or age>limit))
        after_send=bool(watched and (last_sent is None or all(x[1]>last_sent for x in watched)))
        extension=self.extension+(max(0,now-self.blocked_since) if self.blocked_since is not None else 0) if active else 0
        remaining=max(0,pause-(now-last_sent)+extension) if last_sent is not None else 0
        return {'config':dict(self.config),'age':round(age,1) if age is not None else None,
            'limit':limit,'late':late,'fresh':not late,'after_send':after_send,
            'allow':not active or (not late and after_send),
            'sensors':[x[3] for x in watched],'topics':[x[2] for x in watched],
            'extension':round(extension,1),'remaining':remaining}

    def update(self,samples,sources,last_sent,pause,now):
        state=self.snapshot(samples,sources,last_sent,pause,now)
        if not self.config['enabled']:
            self.reset()
            return False
        if state['late']:
            if self.blocked_since is None:
                # Start at the missed deadline, rather than at the next timer tick.
                self.blocked_since=max(now-max(0,(state['age'] or 0)-state['limit']),last_sent if last_sent is not None else float('-inf'))
            return False
        recovered=self.blocked_since is not None
        if recovered:
            self.extension+=max(0,now-self.blocked_since)
            self.blocked_since=None
        return recovered
