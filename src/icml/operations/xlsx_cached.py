"""Reader of cached XLSX cell values, standard-library only; not a formula calculator."""
from zipfile import ZipFile
import posixpath, re, xml.etree.ElementTree as ET
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P='{http://schemas.openxmlformats.org/package/2006/relationships}'

def sheets(path, names=None):
    with ZipFile(path) as z:
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        maps={x.get('Id'):x.get('Target') for x in rels}
        ss=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            ss=[''.join(y.text or '' for y in x.iter(M+'t')) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(M+'si')]
        for sh in workbook.iter(M+'sheet'):
            name=sh.get('name')
            if names is not None and name not in names:continue
            target=maps[sh.get(R+'id')]
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
            root=ET.fromstring(z.read(target))
            rows={}
            for row in root.iter(M+'row'):
                index=int(row.get('r'));cells={}
                for c in row.iter(M+'c'):
                    addr=c.get('r');column=re.match(r'[A-Z]+',addr).group(0)
                    v=c.find(M+'v')
                    if v is not None:
                        value=v.text
                        if c.get('t')=='s':value=ss[int(value)]
                        elif c.get('t') not in ('e','str','inlineStr') and value is not None:
                            try:value=float(value)
                            except (TypeError,ValueError):pass
                    else:
                        inline=c.find(M+'is')
                        value=''.join(t.text or '' for t in inline.iter(M+'t')) if inline is not None else None
                    if value is not None:cells[column]=value
                if cells:rows[index]=cells
            yield name,rows
