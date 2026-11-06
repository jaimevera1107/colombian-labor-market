"""Hito 4: benchmarking LOGO de 14 participaciones laborales sectoriales.

No imputa ni recalibra series ICML. Objetivos = DANE anual departamental 2015-2024.
Variables X = proyecciones de población, PIB de cuentas departamentales y (opcional)
señal urbana observada por DANE (año móvil terminado en diciembre 2021-2024).

El año móvil Dic se usa como una observación de 12 meses, NO como diciembre mensual.
Evaluación LOGO: elimina TODAS las etiquetas del departamento retenido antes de fit.
"""
from __future__ import annotations
import argparse,csv,json,math,unicodedata
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.spatial.distance import jensenshannon
from sklearn.base import clone
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.neighbors import KNeighborsRegressor

SECTORS=['A','B','C','D+E','F','G','H','I','J','K','L','M+N','O+P+Q','R+S+T+U']
GDP_GROUPS=['A','B','C','D+E','F','G+H+I','J','K','L','M+N','O+P+Q','R+S+T']
CITY_MAP={
'Antioquia':'Medellín A.M.','Atlántico':'Barranquilla A.M.','Bolívar':'Cartagena',
'Boyacá':'Tunja','Caldas':'Manizales A.M.','Caquetá':'Florencia','Cauca':'Popayán',
'Cesar':'Valledupar','Chocó':'Quibdó','Córdoba':'Montería','Huila':'Neiva',
'La Guajira':'Riohacha','Magdalena':'Santa Marta','Meta':'Villavicencio',
'Nariño':'Pasto','Norte de Santander':'Cúcuta A.M.','Quindío':'Armenia',
'Risaralda':'Pereira A.M.','Santander':'Bucaramanga A.M.','Sucre':'Sincelejo',
'Tolima':'Ibagué','Valle del Cauca':'Cali A.M.'}
URBAN_FEATURES=['city_tgp_pct','city_to_pct','city_td_pct','city_employed_thousands','city_pet_thousands']

def _csv(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def _norm(s):return ''.join(x for x in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(x)).replace(' ','').replace('.','').replace(',','')

def load_data(sector_csv,pop_csv,gdp_csv,urban_csv=None,max_year=2024,gdp_lag_years=0):
 raw=defaultdict(dict)
 for q in _csv(sector_csv):
  key=(q['department'],int(q['year']));code=q['sector_code'];v=float(q['employed_thousands'])
  if code not in SECTORS or not math.isfinite(v) or v<0:raise ValueError(f'Sector inválido: {q}')
  if code in raw[key]:raise ValueError(f'Sector duplicado {key} {code}')
  raw[key][code]=v
 pop=defaultdict(dict)
 for q in _csv(pop_csv):pop[(_norm(q['dep_name']),int(q['year']))][q['area_type'].strip().lower()]=float(q['population'])
 gdp=defaultdict(dict)
 for q in _csv(gdp_csv):
  key=(_norm(q['department']),int(q['year']));code=q['gdp_code']
  if code in gdp[key]:raise ValueError(f'GDP duplicado {key} {code}')
  gdp[key][code]=float(q['value_billion_cop'])
 urb=defaultdict(dict)
 if urban_csv is not None:
  for q in _csv(urban_csv):
   key=(q['city'].strip(),int(q['year']));code=q['variable']
   if code in urb[key]:raise ValueError(f'Ciudad duplicada {key} {code}')
   urb[key][code]=float(q['value'])
 records=[];missing=[]
 for (dep,yr),sectorvals in sorted(raw.items()):
  if len(sectorvals)!=14:raise ValueError(f'14 sectores requeridos: {dep} {yr}: {len(sectorvals)}')
  if not (2015<=yr<=max_year):continue  # Ajustar disponibilidad de PIB con max_year y rezago.
  pd=pop.get((_norm(dep),yr),{});gd=gdp.get((_norm(dep),yr-gdp_lag_years),{})
  if not all(c in gd for c in GDP_GROUPS) or not ('total' in pd and 'cabecera' in pd):
   missing.append((dep,yr,'GDP o población'));continue
  gp=np.array([gd[c] for c in GDP_GROUPS],float)
  if np.any(~np.isfinite(gp)) or np.any(gp<0) or gp.sum()<=0:raise ValueError(f'GDP inválido {dep}/{yr}')
  sector=np.array([sectorvals[s] for s in SECTORS],float)
  if sector.sum()<=0:raise ValueError(f'Ocupación sectorial no positiva {dep}/{yr}')
  urban=urb.get((CITY_MAP.get(dep,''),yr),{})
  have_urban=all(code in urban for code in URBAN_FEATURES)
  # year, log-pop, urban-share, log PIB per cápita corriente, 12 shares PIB.
  features=[float(yr),math.log(pd['total']),pd['cabecera']/pd['total'],math.log(gp.sum()*1e9/pd['total'])]
  features.extend((gp/gp.sum()).tolist())
  if have_urban:
   features.extend([urban['city_tgp_pct'],urban['city_to_pct'],urban['city_td_pct'],
     # Dividir magnitudes urbanas por población total del dept; evita efecto de escala.
     urban['city_employed_thousands']*1000/pd['total'],urban['city_pet_thousands']*1000/pd['total']])
  records.append({'department':dep,'year':yr,'y':sector/sector.sum(),
   'features_basic':np.asarray(features[:3],float),
   'features_gdp':np.asarray(features,float)[:16],
   'features_urban':np.asarray(features,float) if have_urban else None,
   'has_urban':have_urban,'known_employed_thousands':float(sector.sum()),
   'sector_zero_count':int((sector==0).sum())})
 if missing:raise ValueError(f'Covariables faltantes: {missing[:8]} ({len(missing)} total)')
 return records,{'records':len(records),'territories':len({r['department'] for r in records}),
   'years':sorted({r['year'] for r in records}),'urban_records':sum(r['has_urban'] for r in records),
   'zero_sector_cells':sum(r['sector_zero_count'] for r in records)}

def clr(y,epsilon=1e-6):
 """Transformación log-ratio centrada que admite ceros observados redondeados."""
 x=np.maximum(np.asarray(y,float),epsilon);x=x/x.sum(axis=-1,keepdims=True)
 logs=np.log(x);return logs-logs.mean(axis=-1,keepdims=True)

def inv_clr(z):
 v=np.asarray(z,float);v=v-v.max(axis=-1,keepdims=True);w=np.exp(v)
 # Garantía de positividad en valores continuos; evitar underflow numérico.
 w=np.maximum(w,1e-12);return w/w.sum(axis=-1,keepdims=True)

def _metric(pred,actual):
 pred=np.asarray(pred,float);actual=np.asarray(actual,float)
 return {'mae_sector_pp':float(np.mean(abs(pred-actual))*100),
  'l1_share_pp':float(np.mean(np.sum(abs(pred-actual),axis=1))*100),
  'js_distance':float(np.mean([jensenshannon(a,b,base=2) for a,b in zip(pred,actual)])),
  'positive_fraction':float(np.mean(pred>0))}

def benchmark(records,range_name,years,with_urban=False,seed=2026):
 subset=[r for r in records if r['year'] in years and (r['has_urban'] if with_urban else True)]
 depts=sorted({r['department'] for r in subset})
 if len(depts)<10:raise ValueError('Pocos departamentos para LOGO')
 if len(subset)!=len(depts)*len(years):raise ValueError('LOGO desbalanceado o años faltantes')
 preds=[]
 specs=[('media_anual',None,'features_basic'),
        ('ridge_demografia',make_pipeline(StandardScaler(),Ridge(alpha=20)),'features_basic'),
        ('ridge_pib',make_pipeline(StandardScaler(),Ridge(alpha=30)),'features_gdp'),
        ('knn_pib',make_pipeline(StandardScaler(),KNeighborsRegressor(n_neighbors=5,weights='distance')),'features_gdp'),
        ('extra_trees_pib',ExtraTreesRegressor(n_estimators=90,min_samples_leaf=3,max_features=.85,random_state=seed,n_jobs=1),'features_gdp')]
 if with_urban:
  specs.extend([('ridge_pib_ciudad',make_pipeline(StandardScaler(),Ridge(alpha=30)),'features_urban'),
                ('extra_trees_pib_ciudad',ExtraTreesRegressor(n_estimators=90,min_samples_leaf=3,max_features=.85,random_state=seed,n_jobs=1),'features_urban')])
 for held in depts:
  tr=[r for r in subset if r['department']!=held];te=[r for r in subset if r['department']==held]
  ytrain=np.stack([r['y'] for r in tr]);actual=np.stack([r['y'] for r in te]); years_tr=[r['year'] for r in tr]
  for model,est,features in specs:
   if est is None:
    prediction=np.stack([np.mean(ytrain[np.asarray(years_tr)==r['year']],axis=0) for r in te])
    prediction=np.maximum(prediction,1e-12);prediction=prediction/prediction.sum(axis=1,keepdims=True)
   else:
    X=np.stack([r[features] for r in tr]);Xt=np.stack([r[features] for r in te])
    fitted=clone(est)
    fitted.fit(X,clr(ytrain))
    prediction=inv_clr(fitted.predict(Xt))
   for rr,obs,phat in zip(te,actual,prediction):
    for j,sector in enumerate(SECTORS):
     preds.append({'experiment':range_name,'department':held,'year':rr['year'],
       'model':model,'sector_code':sector,'observed_share':float(obs[j]),
       'predicted_share':float(phat[j]),'abs_error_pp':float(abs(phat[j]-obs[j])*100)})
 summaries=[];dep_metrics=[];sector_metrics=[]
 models=sorted({x['model'] for x in preds})
 for mod in models:
  group=[p for p in preds if p['model']==mod]
  for dep in depts:
   pg=[p for p in group if p['department']==dep]
   err=np.array([p['abs_error_pp'] for p in pg])
   dep_metrics.append({'experiment':range_name,'model':mod,'department':dep,
      'mae_sector_pp':float(err.mean()),'p90_sector_ae_pp':float(np.percentile(err,90))})
  for s in SECTORS:
   pg=[p for p in group if p['sector_code']==s];err=np.array([p['abs_error_pp'] for p in pg])
   sector_metrics.append({'experiment':range_name,'model':mod,'sector_code':s,
      'mae_pp':float(err.mean()),'p90_ae_pp':float(np.percentile(err,90))})
  by=defaultdict(dict);obs=defaultdict(dict)
  for p in group:
   by[(p['department'],p['year'])][p['sector_code']]=p['predicted_share']
   obs[(p['department'],p['year'])][p['sector_code']]=p['observed_share']
  a=np.array([[obs[k][s] for s in SECTORS] for k in sorted(by)])
  b=np.array([[by[k][s] for s in SECTORS] for k in sorted(by)])
  score=_metric(b,a)
  summaries.append({'experiment':range_name,'model':mod,'n_departments':len(depts),
      'n_department_year':len(by),'n_sector_cells':len(group),
      **score,'worst_department_mae_pp':max(q['mae_sector_pp'] for q in dep_metrics if q['model']==mod and q['experiment']==range_name)})
 return preds,summaries,dep_metrics,sector_metrics

def _save(path,items):
 if not items:return
 with open(path,'w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)


def space_time_holdout_2025(rows,seed=2026):
 """2025 no aparece en entrenamiento, y se retira todo el departamento objetivo.

 La variable PIB es de AÑO ANTERIOR: 2014-2023 para train, 2024 para test.
 Es una prueba retrospectiva con PIB publicado, no 'as-of' producción en tiempo real.
 """
 depts=sorted({r['department'] for r in rows if r['year']==2025})
 predictions=[]
 specs=[('media_otras_2024',None),
        ('ridge_demografia',make_pipeline(StandardScaler(),Ridge(alpha=20))),
        ('ridge_pib_rezagado',make_pipeline(StandardScaler(),Ridge(alpha=30))),
        ('extra_trees_pib_rezagado',ExtraTreesRegressor(n_estimators=90,min_samples_leaf=3,max_features=.85,random_state=seed,n_jobs=1))]
 for held in depts:
  training=[r for r in rows if r['department']!=held and r['year']<=2024]
  test=[r for r in rows if r['department']==held and r['year']==2025]
  if len(test)!=1:raise ValueError(f'Objetivo 2025 faltante {held}')
  test=test[0]
  all_2024=[r['y'] for r in training if r['year']==2024]
  if len(all_2024)!=len(depts)-1:raise ValueError('2024 incompleto en entrenamiento')
  ytrain=np.stack([r['y'] for r in training])
  for model,reg in specs:
   if reg is None:p=np.mean(all_2024,axis=0);p=np.maximum(p,1e-12);p/=p.sum()
   else:
    features='features_basic' if model=='ridge_demografia' else 'features_gdp'
    X=np.stack([r[features] for r in training]);xt=test[features][None,:]
    fitted=clone(reg);fitted.fit(X,clr(ytrain))
    p=inv_clr(fitted.predict(xt))[0]
   for j,sector in enumerate(SECTORS):
    predictions.append({'experiment':'logo_space_time_2025_gdp_lag1','department':held,'year':2025,
      'model':model,'sector_code':sector,'observed_share':float(test['y'][j]),
      'predicted_share':float(p[j]),'abs_error_pp':float(abs(p[j]-test['y'][j])*100)})
 summaries=[]
 for model in sorted(set(x['model'] for x in predictions)):
  p=[x for x in predictions if x['model']==model]
  by=defaultdict(dict);obs=defaultdict(dict)
  for x in p:
   by[x['department']][x['sector_code']]=x['predicted_share']
   obs[x['department']][x['sector_code']]=x['observed_share']
  a=np.asarray([[obs[d][s] for s in SECTORS] for d in sorted(by)])
  b=np.asarray([[by[d][s] for s in SECTORS] for d in sorted(by)])
  score=_metric(b,a)
  summaries.append({'experiment':'logo_space_time_2025_gdp_lag1','model':model,
   'n_departments':len(depts),'n_department_year':len(depts),'n_sector_cells':len(p),
   **score,'worst_department_mae_pp':float(max(np.mean([x['abs_error_pp'] for x in p if x['department']==d]) for d in by))})
 return predictions,summaries

def run(sector_csv,pop_csv,gdp_csv,urban_csv,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 rows,diagnostics=load_data(sector_csv,pop_csv,gdp_csv,urban_csv)
 jobs=[('logo_sector_2015_2024',list(range(2015,2025)),False),
       ('logo_sector_2021_2024',list(range(2021,2025)),False),
       ('logo_sector_2021_2024_urban',list(range(2021,2025)),True)]
 pred=[];summary=[];dep=[];sec=[]
 for name,years,urban in jobs:
  a,b,c,d=benchmark(rows,name,years,urban)
  pred.extend(a);summary.extend(b);dep.extend(c);sec.extend(d)
 rows_lag,lag_diag=load_data(sector_csv,pop_csv,gdp_csv,urban_csv,max_year=2025,gdp_lag_years=1)
 future_pred,future_summary=space_time_holdout_2025(rows_lag)
 pred.extend(future_pred);summary.extend(future_summary)
 _save(out/'sector_logo_predictions.csv',pred)
 _save(out/'sector_logo_summary.csv',summary)
 _save(out/'sector_logo_departments.csv',dep)
 _save(out/'sector_logo_by_branch.csv',sec)
 with open(out/'hito4_report.json','w',encoding='utf-8') as f:
  json.dump({'source':'DANE GEIH departmental annual official sectors 2015–2025',
     'evaluation_years':'2015–2024; separate 2021–2024 city experiment',
     'target':'14 industry shares among classified employment (No informa excluded)',
     'model_selection':'exploratory only; no nested cross-validation or temporal holdout yet',
     'urban_window':'12-month mobile year ending in December, not a monthly observation',
     'geography':'LOGO excludes target observations of entire department; urban signal permissible',
     'diagnostics':diagnostics,'lagged_diagnostics':lag_diag,'metrics':summary},f,ensure_ascii=False,indent=2)
 return summary

def main():
 a=argparse.ArgumentParser();a.add_argument('--sector-csv',required=True);a.add_argument('--population-csv',required=True)
 a.add_argument('--gdp-csv',required=True);a.add_argument('--urban-csv',required=True);a.add_argument('--out',required=True)
 p=a.parse_args();result=run(p.sector_csv,p.population_csv,p.gdp_csv,p.urban_csv,p.out)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

# Diagnostics intentionally separate from model fitting and never claimed as validation
# of unobserved departments. No target labels are read for these territories.
def support_diagnostics_2024(pop_csv,gdp_csv,observed_departments,out_csv):
 from scipy.spatial.distance import cdist
 pop=defaultdict(dict)
 for q in _csv(pop_csv):pop[(_norm(q['dep_name']),int(q['year']))][q['area_type'].strip().lower()]=float(q['population'])
 gdp=defaultdict(dict)
 for q in _csv(gdp_csv):gdp[(_norm(q['department']),int(q['year']))][q['gdp_code']]=float(q['value_billion_cop'])
 alias={'bogotadc':'bogotadc','bogotad.c.':'bogotadc',
  'sanandresprovidenciaysantacatalina(archipielago)':'archipielagodesanandres'}
 feat={};names={}
 for q in _csv(gdp_csv):
  if int(q['year'])!=2024:continue
  d=_norm(q['department']);names[d]=q['department']
 for d,fields in gdp.items():
  nm,yr=d
  if yr!=2024 or any(k not in fields for k in GDP_GROUPS):continue
  demographics=pop.get((nm,yr),{})
  if not demographics:
   replacement=alias.get(nm)
   if replacement:demographics=pop.get((replacement,yr),{})
  if not demographics or 'total' not in demographics or 'cabecera' not in demographics:continue
  pp=demographics['total'];gg=np.array([fields[k] for k in GDP_GROUPS],float)
  feat[nm]=np.r_[np.log(pp),demographics['cabecera']/pp,np.log(gg.sum()*1e9/pp),gg/gg.sum()]
 observed={_norm(x) for x in observed_departments}
 known=sorted(k for k in feat if k in observed)
 unknown=sorted(k for k in feat if k not in observed)
 if len(known)!=23:raise ValueError(f'Esperados 23 territorios observados; encontrados {len(known)}')
 sc=StandardScaler().fit(np.stack([feat[k] for k in known]))
 train=sc.transform(np.stack([feat[k] for k in known]))
 near=cdist(train,train);np.fill_diagonal(near,np.inf)
 baseline=near.min(axis=1)
 q95=float(np.percentile(baseline,95))
 items=[]
 for d in unknown:
  z=sc.transform(feat[d][None,:]); dist=cdist(z,train)[0]
  ix=int(np.argmin(dist))
  items.append({'territory':names[d],'year':2024,'nearest_official_department':names[known[ix]],
    'distance_standardized':float(dist[ix]),'train_loo_distance_p95':q95,
    'outside_95pct_neighbor_support':bool(float(dist[ix])>q95),
    'official_departmental_sector_label_available':False})
 _save(out_csv,items)
 return {'nonobserved_territories_scored':len(items),
  'outside_neighbor_support':sum(x['outside_95pct_neighbor_support'] for x in items),
  'threshold':q95}


def paired_department_bootstrap(department_rows,exp='logo_sector_2015_2024',
       base='media_anual',candidate='ridge_pib',seed=2026,n_boot=2000):
 """CI diagnóstico de mejoría, remuestreando departamentos, no celdas correlacionadas."""
 src={(r['department'],r['model']):r for r in department_rows if r['experiment']==exp}
 dep=sorted({k[0] for k in src})
 differences=np.array([float(src[(d,base)]['mae_sector_pp'])-float(src[(d,candidate)]['mae_sector_pp']) for d in dep])
 rng=np.random.default_rng(seed)
 samples=rng.choice(differences,size=(n_boot,len(dep)),replace=True).mean(axis=1)
 return {'experiment':exp,'base':base,'candidate':candidate,'n_departments':len(dep),
  'mean_improvement_pp':float(differences.mean()),
  'bootstrap_ci95_low_pp':float(np.percentile(samples,2.5)),
  'bootstrap_ci95_high_pp':float(np.percentile(samples,97.5)),
  'departments_improved':int(np.count_nonzero(differences>0)),
  'interpretation':'diagnóstico exploratorio, no inferencia causal ni selección final'}
