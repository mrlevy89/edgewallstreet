import re,sys,html.parser
o=open(sys.argv[1],encoding='utf-8').read(); n=open(sys.argv[2],encoding='utf-8').read(); want=sys.argv[3]
errs=[]
def blocks(s,p): return re.findall(p,s,flags=re.S)
for name,p in [('script',r'<script\b.*?</script>'),('style',r'<style\b.*?</style>'),('static tool',r'<!-- STATIC TOOL: DO NOT REGENERATE -->.*?<!-- /STATIC TOOL -->')]:
    if blocks(o,p)!=blocks(n,p): errs.append(name+' blocks changed')
tp=r'id="(tab-[a-z]+)"'
if re.findall(tp,o)!=re.findall(tp,n): errs.append('tabpanel ids changed')
for k in ['deploy-open','Wall Street has an edge. Now so do you.','id="g-ticker"','id="themeTgl"','class="tabbar']:
    if (k in o) and (k not in n): errs.append('missing '+k)
r=len(n)/len(o)
if not 0.9<r<1.1: errs.append('size ratio %.3f'%r)
m=re.search(r'<div class="date">(.*?)</div>',n)
if not m or m.group(1).replace('&middot;','·')!=want: errs.append('date line is %r, want %r'%(m and m.group(1),want))
def prose(s):
    s=re.sub(r'<script\b.*?</script>','',s,flags=re.S); return re.sub(r'<style\b.*?</style>','',s,flags=re.S)
po,pn=prose(o),prose(n)
for ch in ['—','–']:
    if pn.count(ch)>po.count(ch): errs.append('added %d long dashes'%(pn.count(ch)-po.count(ch)))
emo=r'[\U0001F300-\U0001FAFF☀-➿]'
if len(re.findall(emo,pn))>len(re.findall(emo,po)): errs.append('emoji added')
if (n.count('<div')-n.count('</div>'))!=(o.count('<div')-o.count('</div>')): errs.append('div balance changed')
if not n.strip().lower().endswith('</html>'): errs.append('file does not end with </html>')
html.parser.HTMLParser().feed(n)
if errs: print('VALIDATION FAILED:\n- '+'\n- '.join(errs)); sys.exit(1)
print('VALIDATION PASSED')
