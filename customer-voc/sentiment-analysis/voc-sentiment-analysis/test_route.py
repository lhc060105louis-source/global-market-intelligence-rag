from rag_service import RagService
rag = RagService.from_env()
text = 'You need to recharge electric vehicles (of course), and the recharging systems I am informed of require electronic money. Not all people have it. (And not all people accept leaving a DB track of their stops.) "Cheap" makes no sense here - you may have misunderstood the post. Whether charging costs 1 penny or 1 grand, it is still inaccessible if the plugs are automated totems not accepting cash.'
decision = rag.route(text)
print(f'Action: {decision.action}')
for m, s in decision.matches:
    if m.source_type == 'synthetic_seed':
        print(f'Score: {s:.4f} | Topic: {m.topic_id} | Text: {m.text}')
