"""Territorial-sectoral predictor: faithful evaluation of the original signals and a reconciled monthly matrix.

Experimental results, NOT canonical series. Annual GEIH shares are never
mixed with full-universe national levels as hard constraints.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor
from .predictive_benchmark import features_all_33, clamp_simplex
from .predictive_reference import _norm, clr, inv_clr
from icml.domain.cutoff import LAST_YEAR, N_MONTHS

SECTORS14=['A','B','C','D_E','F','G','H','I','J','K','L','M_N','O_P_Q','R_S_T_U']
SECTORS15=SECTORS14+['NO_INFO']
ALIAS={'D+E':'D_E','M+N':'M_N','O+P+Q':'O_P_Q','R+S+T+U':'R_S_T_U'}
# Copied from the original notebook: 38 features, including the two that are
# problematic for transfer (numeric dep_code and vintage informality).
ORIGINAL38=['dep_code','year','month','population','pet','pea','employed','unemployed','inactive','informals','formals',
 'employment_rate','unemployment_rate','participation_rate','inactivity_rate','informality_rate',
 'participation_rate_cluster','employment_rate_cluster','unemployment_rate_cluster','inactivity_rate_cluster',
 'pet_cluster_mean','pet_resid_cluster','pet_cluster_ratio','pea_cluster_mean','pea_resid_cluster','pea_cluster_ratio',
 'employed_cluster_mean','employed_resid_cluster','employed_cluster_ratio','unemployed_cluster_mean',
 'unemployed_resid_cluster','unemployed_cluster_ratio','inactive_cluster_mean','inactive_resid_cluster',
 'inactive_cluster_ratio','population_cluster_mean','population_resid_cluster','population_cluster_ratio']
assert len(ORIGINAL38)==38
# The original dictionary repeated 50 (Meta) and 20 (Cesar): Python keeps the
# last assignment. These rules preserve the effective semantics explicitly.
GROUPS={
 5:'core_observed',8:'core_observed',11:'core_observed',25:'core_observed',76:'core_observed',
 13:'large_consistent',23:'large_consistent',68:'large_consistent',47:'large_consistent',
 27:'choco_cluster',19:'choco_cluster',88:'choco_cluster',91:'choco_cluster',
 41:'huila_cluster',73:'huila_cluster',86:'huila_cluster',18:'huila_cluster',
 15:'quindio_cluster',63:'quindio_cluster',70:'sucre_cluster',44:'sucre_cluster',99:'sucre_cluster',
 17:'risaralda_cluster',66:'risaralda_cluster',52:'nariño_cluster',85:'nariño_cluster',94:'nariño_cluster',
 54:'norte_cluster',81:'norte_cluster',95:'norte_cluster',
 50:'meta_cluster',20:'meta_cluster',97:'meta_cluster'}


def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()


def load_labor_features(root):
 d=pd.read_csv(root/'inputs/departamentos.csv',usecols=['period','dep_code','employed','unemployed','inactive','labor_force','working_age','population'])
 d=d.rename(columns={'labor_force':'pea','working_age':'pet'})
 d['date']=pd.to_datetime(d.period+'-01');d['year']=d.date.dt.year;d['month']=d.date.dt.month
 if d[['dep_code','period']].duplicated().any() or len(d)!=33*N_MONTHS:raise ValueError('Invalid ICML panel')
 old=pd.read_csv(root/'inputs/informalidad_departamental_vintage_original_2007_2025.csv',usecols=['dep_code','date','employed','informals','formals','informality_rate'])
 old['date']=pd.to_datetime(old.date)
 old['informality_rate']=np.where(old.employed>0,old.informals/old.employed,np.nan)
 if old[['dep_code','date']].duplicated().any():raise ValueError('Informalidad vintage duplicada')
 old=old[['dep_code','date','informality_rate']]
 d=d.merge(old,on=['dep_code','date'],how='left',validate='one_to_one')
 d['informality_rate']=d.informality_rate.where(d.informality_rate.between(0,1))
 d['informality_missing']=d.informality_rate.isna().astype('int8')
 d['informals']=d.employed*d.informality_rate
 d['formals']=d.employed*(1-d.informality_rate)
 d['employment_rate']=d.employed/d.pet.where(d.pet>0)
 d['unemployment_rate']=d.unemployed/d.pea.where(d.pea>0)
 d['participation_rate']=d.pea/d.pet.where(d.pet>0)
 d['inactivity_rate']=d.inactive/d.pet.where(d.pet>0)
 d['dep_cluster']=d.dep_code.map(GROUPS)
 if d.dep_cluster.isna().any():raise ValueError('Falta grupo territorial original')
 for v in ['participation_rate','employment_rate','unemployment_rate','inactivity_rate']:
  d[v+'_cluster']=d.groupby(['dep_cluster','year'])[v].transform('median')
 for v in ['pet','pea','employed','unemployed','inactive','population']:
  base=d.groupby(['dep_cluster','year'])[v].transform('median')
  d[v+'_cluster_mean']=base
  d[v+'_resid_cluster']=d[v]-base
  d[v+'_cluster_ratio']=d[v]/base.where(base>0)
 # Instead of passing monthly information off as an annual observation,
 # the variables are aggregated explicitly (mean of the 12 months).
 cols=[x for x in ORIGINAL38 if x not in ('dep_code','year')]+['informality_missing']
 annual=d.groupby(['dep_code','year'],as_index=False)[cols].mean()
 annual['year']=annual.year.astype(int)
 if len(annual)!=33*(LAST_YEAR-1992): # 1993..2026 = 34 years, but 2026 is incomplete
  raise ValueError(f'Panel anual ICML incompleto: {len(annual)}')
 return annual,d


def training_panel(root,annual):
 allf=features_all_33(root)
 gx=pd.DataFrame([{'dep_code':f['dep_code'],'year':f['year'],
                   **{f'gdp_{j:02d}':v for j,v in enumerate(f['features_gdp'])}} for f in allf])
 cols=[f'gdp_{j:02d}' for j in range(16)]
 f=annual.merge(gx,on=['dep_code','year'],validate='one_to_one',how='inner')
 official=pd.read_csv(root/'inputs/official_sectors_2015_2025.csv')
 official['sector_code']=official.sector_code.replace(ALIAS)
 mapping=pd.read_csv(root/'inputs/15_candidatos_anuales_33_territorios.csv',usecols=['department','dep_code']).drop_duplicates('dep_code')
 official['dep_key']=official.department.map(_norm);mapping['dep_key']=mapping.department.map(_norm)
 # Geographic exactness: names from the official file, NEVER assignment by position.
 names=mapping[['dep_key','dep_code']].drop_duplicates('dep_key')
 official=official.merge(names,on='dep_key',validate='many_to_one',how='left')
 if official.dep_code.isna().any():raise ValueError('DANE department without a homologated code')
 pv=official.pivot(index=['dep_code','year'],columns='sector_code',values='employed_thousands').reindex(columns=SECTORS14)
 if pv.shape!=(23*11,14) or pv.isna().any().any():raise ValueError(f'Anclas DANE incompletas: {pv.shape}')
 pv=pv.div(pv.sum(axis=1),axis=0).reset_index()
 obs=f.merge(pv,on=['dep_code','year'],validate='one_to_one')
 if len(obs)!=23*11:raise ValueError('Entrenamiento no es 23x11')
 return f,obs,cols


def predictor_feature_names(gdp_cols,include_dep):
 cols=gdp_cols+[f'original_{x}' for x in ORIGINAL38 if include_dep or x!='dep_code']+['informality_missing']
 return cols


def vector(df,gdp_cols,include_dep):
 tmp=df.rename(columns={c:'original_'+c for c in ORIGINAL38 if c not in ('dep_code','year')}).copy()
 tmp['original_year']=tmp.year;tmp['original_dep_code']=tmp.dep_code
 cols=predictor_feature_names(gdp_cols,include_dep)
 arr=tmp[cols].to_numpy(dtype=float)
 if np.isinf(arr).any():raise ValueError('Variables infinitas')
 return arr,cols


def estimator(family='ridge'):
 # Predefined parameters; no tuning on held-out folds nor on the year 2025.
 if family=='ridge':
  return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),Ridge(alpha=75.))
 if family=='xgb':
  base=XGBRegressor(n_estimators=100,max_depth=3,learning_rate=.06,subsample=.8,
       colsample_bytree=.8,random_state=42,n_jobs=1,tree_method='hist',
       multi_strategy='one_output_per_tree',objective='reg:squarederror')
  # Native XGBoost trains one tree per branch and boosting round; it avoids the
  # overhead of 14 wrappers without changing the independence of the outputs.
  return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),base)
 raise ValueError(family)


def fit_predict(train,test,gdp_cols,include_dep,family='ridge'):
 X,feature_cols=vector(train,gdp_cols,include_dep)
 T,_=vector(test,gdp_cols,include_dep)
 y=train[SECTORS14].to_numpy(float)
 mod=estimator(family)
 y=np.maximum(y,1e-10)/np.maximum(y,1e-10).sum(axis=1,keepdims=True)
 mod.fit(X,clr(y) if family=='ridge' else y)
 out=mod.predict(T)
 return clamp_simplex(inv_clr(out) if family=='ridge' else out),mod,feature_cols


def logo(obs,gdp_cols):
 predictions=[]
 for dep in sorted(obs.dep_code.unique()):
  train=obs[(obs.dep_code!=dep)&(obs.year<=2024)]
  test=obs[obs.dep_code==dep].sort_values('year')
  if len(train)!=220 or len(test)!=11:raise AssertionError('Fuga/cobertura LOGO')
  for name,include_dep,family in [('ridge_original38_gdp',True,'ridge'),('ridge_original37_sin_id_gdp',False,'ridge'),('xgb14_original38_gdp',True,'xgb')]:
   pred,_,_=fit_predict(train,test,gdp_cols,include_dep,family)
   for k,r in enumerate(test.itertuples(index=False)):
    for s,p in zip(SECTORS14,pred[k]):
     predictions.append({'dep_code':int(dep),'year':int(r.year),'sector_code':s,'model':name,
             'observed_share':float(getattr(r,s)),'predicted_share':float(p),
             'test_protocol':'LOGO_2015_2024' if r.year<=2024 else 'LOGO_2025_HELD_OUT'})
 return pd.DataFrame(predictions)


def evaluate(oof,root):
 original=pd.read_csv(root/'inputs/15_predicciones_oof.csv')
 original['sector_code']=original.sector_code.replace(ALIAS)
 codes=pd.read_csv(root/'inputs/15_candidatos_anuales_33_territorios.csv',usecols=['department','dep_code']).drop_duplicates('department')
 original['dep_key']=original.department.map(_norm)
 codes['dep_key']=codes.department.map(_norm)
 original=original.merge(codes[['dep_key','dep_code']].drop_duplicates('dep_key'),on='dep_key',validate='many_to_one')
 if original.dep_code.isna().any() or original.dep_code.nunique()!=23:raise ValueError('Mapeo H15 LOGO de 23 departamentos incorrecto')
 original=original[original.model.eq('ridge_clr_pib_rezagado')].copy()
 original=original.rename(columns={'model':'model_h15','experiment':'test_protocol_h15'})
 original['model']='ridge_h15_gdp_baseline'
 original['test_protocol']=original.test_protocol_h15.map({'LOGO_2015_2024':'LOGO_2015_2024','LOGO_PLUS_FUTURE_2025':'LOGO_2025_HELD_OUT'})
 assert len(original)==23*11*14
 use=pd.concat([oof,original[oof.columns]],ignore_index=True)
 idx=['dep_code','year','sector_code','test_protocol']
 src=use[use.model.isin(['ridge_h15_gdp_baseline','xgb14_original38_gdp'])]
 wide=src.pivot(index=idx,columns='model',values='predicted_share')
 if wide.isna().any().any() or len(wide)!=23*11*14:raise ValueError('El ensamble no tiene exactamente las mismas celdas')
 y=src.drop_duplicates(idx).set_index(idx).loc[wide.index,'observed_share']
 # Predefined weight grid; 2025 plays no part in its choice.
 grid=np.array([0.,0.25,0.5,0.75,1.])
 train=(wide.index.get_level_values('year')<=2024)
 loss={float(alpha):float(100*np.mean(np.abs((1-alpha)*wide['ridge_h15_gdp_baseline'].to_numpy()[train]
                        +alpha*wide['xgb14_original38_gdp'].to_numpy()[train]-y.to_numpy()[train]))) for alpha in grid}
 alpha=min(loss,key=lambda x:(loss[x],x))
 blended=((1-alpha)*wide['ridge_h15_gdp_baseline']+alpha*wide['xgb14_original38_gdp']).rename('predicted_share')
 en=blended.reset_index()
 en['observed_share']=y.to_numpy()
 en['model']='ensamble_h15_gdp_xgb38'
 use=pd.concat([use,en[use.columns]],ignore_index=True)
 use['error_abs_pp']=100*np.abs(use.predicted_share-use.observed_share)
 sc=use.groupby(['model','test_protocol'],as_index=False).agg(mae_pp=('error_abs_pp','mean'),max_pp=('error_abs_pp','max'),n=('error_abs_pp','size'))
 bydep=use.groupby(['model','test_protocol','dep_code'],as_index=False).agg(mae_pp=('error_abs_pp','mean'))
 return use,sc,bydep,alpha,loss


def annual_candidates(root,feature,obs,gdp_cols,chosen,alpha):
 if chosen in ('ridge_h15_gdp_baseline','ensamble_h15_gdp_xgb38'):
  d=pd.read_csv(root/'inputs/15_candidatos_anuales_33_territorios.csv')
  d=d[d.model.eq('ridge_clr_pib_rezagado')].copy()
  d=d.rename(columns={'predicted_share':'share_model'})
  d['model']=chosen
  if chosen=='ensamble_h15_gdp_xgb38':
   pred,_,_=fit_predict(obs[obs.year<=2024],feature,gdp_cols,True,'xgb')
   rows=[]
   for r,p in zip(feature[['year','dep_code']].itertuples(index=False),pred):
    for sec,v in zip(SECTORS14,p):rows.append({'year':r.year,'dep_code':r.dep_code,'sector_code':sec,'share_xgb38':v})
   xgb=pd.DataFrame(rows)
   d=d.merge(xgb,on=['year','dep_code','sector_code'],validate='one_to_one')
   d['share_model']=(1-alpha)*d.share_model+alpha*d.share_xgb38
   d['share_model']/=d.groupby(['dep_code','year']).share_model.transform('sum')
  return d[['year','dep_code','sector_code','share_model','model']]
 inc=chosen in ('ridge_original38_gdp','xgb14_original38_gdp')
 family='xgb' if chosen=='xgb14_original38_gdp' else 'ridge'
 pred,_,_=fit_predict(obs[obs.year<=2024],feature,gdp_cols,inc,family)
 rows=[]
 for r,p in zip(feature[['year','dep_code']].itertuples(index=False),pred):
  for s,v in zip(SECTORS14,p):rows.append({'year':r.year,'dep_code':r.dep_code,'sector_code':s,'share_model':v,'model':chosen})
 return pd.DataFrame(rows)


def annual_target_table(root,cand,anchor_strength=0.8):
 # The GEIH anchors are kept as evidence; their injection is SOFT and only for
 # the historical elaboration, never in the out-of-sample evaluation.
 # In production the observed annual figure is not read as a full ICML share.
 obs=pd.read_csv(root/'inputs/official_sectors_2015_2025.csv')
 obs['sector_code']=obs.sector_code.replace(ALIAS)
 names=pd.read_csv(root/'inputs/15_candidatos_anuales_33_territorios.csv',usecols=['department','dep_code']).drop_duplicates('department')
 obs['dep_key']=obs.department.map(_norm);names['dep_key']=names.department.map(_norm)
 obs=obs.merge(names[['dep_key','dep_code']].drop_duplicates('dep_key'),on='dep_key',validate='many_to_one')
 if obs.dep_code.isna().any() or obs.dep_code.nunique()!=23:raise ValueError('Mapeo anclas DANE 23 departamentos incorrecto')
 obs['obs_share']=obs.employed_thousands/obs.groupby(['dep_code','year']).employed_thousands.transform('sum')
 obs['reference_source']='DANE_GEIH_DEPARTMENT_23_FROM_ORIGINAL_ICML'
 # Bogotá is NOT used to train/select: the independent evidence may inform the
 # historical reconstruction only after the evaluation.
 bg=pd.read_csv(root/'inputs/14_referencia_externa_Bogota_DANE_GEIH_2015_2024.csv')
 bg=bg.rename(columns={'group_code':'sector_code'})
 bg['obs_share']=bg.observed_share_pct/bg.groupby('year').observed_share_pct.transform('sum')
 bg['reference_source']='DANE_GEIH_BOGOTA_ANUARIO_2015_2024_INDEPENDENT'
 obs=pd.concat([obs[['dep_code','year','sector_code','obs_share','reference_source']],
             bg[['dep_code','year','sector_code','obs_share','reference_source']]],ignore_index=True)
 if obs.duplicated(['dep_code','year','sector_code']).any() or len(obs)!=(23*11+10)*14:
  raise ValueError('Duplicated anchors or wrong Bogotá coverage')
 d=cand.merge(obs,on=['dep_code','year','sector_code'],how='left',validate='one_to_one')
 strengths=np.where(d.reference_source.eq('DANE_GEIH_BOGOTA_ANUARIO_2015_2024_INDEPENDENT'),1.0,anchor_strength)
 d['share_anchored']=np.where(d.obs_share.notna(),(1-strengths)*d.share_model+strengths*d.obs_share,d.share_model)
 d['share_anchored']/=d.groupby(['dep_code','year']).share_anchored.transform('sum')
 d['anchor_status']=np.where(d.reference_source.eq('DANE_GEIH_BOGOTA_ANUARIO_2015_2024_INDEPENDENT'),
       'GEIH_BOGOTA_INDEPENDENT_ANNUAL_REFERENCE_SOFT_AFTER_RECONCILIATION',
       np.where(d.obs_share.notna(),'GEIH_DEPARTMENT_ANNUAL_SOFT_ANCHOR','PREDICTED_NO_ANCHOR'))
 return d


def ipf(seed,row_targets,col_targets,tol=1e-10,max_iter=2000):
 """Biproportional balancing with structural national zeros; exact row/column.
 Rows = departamento ocupados ICML completos. Columns = total*cuotas H11.
 """
 rows=np.asarray(row_targets,float);cols=np.asarray(col_targets,float);x=np.asarray(seed,float).copy()
 if np.any(rows<0) or np.any(cols<0) or not np.isfinite(x).all():raise ValueError('Invalid margins')
 if not np.isclose(rows.sum(),cols.sum(),rtol=1e-11,atol=0):raise ValueError('Incompatible margins')
 if rows.sum()==0:return np.zeros_like(x),0
 positive=cols>1e-13
 x[:,~positive]=0.
 x[:,positive]=np.maximum(x[:,positive],1e-12)
 for it in range(max_iter):
  r=x.sum(axis=1)
  x*=np.divide(rows,r,out=np.zeros_like(rows),where=r>0)[:,None]
  c=x.sum(axis=0)
  x[:,positive]*=(cols[positive]/c[positive])[None,:]
  if it%10==0:
   e=max(np.max(np.abs(x.sum(axis=1)-rows)),np.max(np.abs(x.sum(axis=0)-cols)))/max(rows.sum(),1)
   if e<tol:break
 else:raise RuntimeError('IPF did not converge')
 # correction exact row final, national tolerance enforced at scale ~1e-9
 return x,it+1


def month_curve(base,annual,month_info,national,first=1993,last=LAST_YEAR,half_life_years=12.):
 """34-year prior; no pseudo-official monthly sector anchors.
 Within a year national H11 sets shape. For 1993-2014, the log-odds
 territorial difference relative to H11 at 2015 is transferred backward
 with documented exponential attenuation (sensitivity hypothesis).
 """
 dep_codes=sorted(base.dep_code.unique())
 years=sorted(base.year.unique())
 if years[0]!=first or years[-1]!=last:raise ValueError('Unexpected employment years')
 tab=annual.pivot(index=['dep_code','year'],columns='sector_code',values='share_anchored').reindex(columns=SECTORS14)
 if tab.isna().any().any():raise ValueError('Candidatos anuales incompletos')
 nat=national.pivot(index='period',columns='sector_code',values='sector_share').reindex(columns=SECTORS15)
 if nat.isna().any().any():raise ValueError('Incomplete national composition')
 nat.index=nat.index.astype(str)
 # aggregate national proportions of classified employment by year (unweighted month approximation).
 nn=nat[SECTORS14].copy();nn=nn.div(nn.sum(axis=1),axis=0)
 nn['year']=nn.index.str[:4].astype(int)
 annualnat=nn.groupby('year')[SECTORS14].mean()
 for dep in dep_codes:
  if (dep,2015) not in tab.index:raise ValueError('2015 is missing for the splice')
 for period,group in base.groupby('period',sort=True):
  yr=int(period[:4]);sectors_n=nat.loc[period].to_numpy(float)
  if yr<=2014:
   attenuation=(np.exp(-np.log(2)*(2015-yr)/half_life_years) if half_life_years is not None else 1.)
   offsets=np.vstack([np.log(np.maximum(tab.loc[(dep,2015)].to_numpy(float),1e-10)/np.maximum(annualnat.loc[2015].to_numpy(float),1e-10))*attenuation for dep in dep_codes])
   status='BACKCAST_PRE2015_ASSUMED_TERRITORIAL_TRENDS'
  elif yr==LAST_YEAR:
   offsets=np.vstack([np.log(np.maximum(tab.loc[(dep,2025)].to_numpy(float),1e-10)/np.maximum(annualnat.loc[2025].to_numpy(float),1e-10)) for dep in dep_codes])
   status='2026_LAST_AVAILABLE_2025_ANNUAL_PROFILE'
  else:
   offsets=np.vstack([np.log(np.maximum(tab.loc[(dep,yr)].to_numpy(float),1e-10)/np.maximum(annualnat.loc[yr].to_numpy(float),1e-10)) for dep in dep_codes])
   status='ANNUAL_PREDICTION_AND_WHERE_AVAILABLE_SOFT_ANCHOR'
  arr=np.exp(np.clip(offsets,-20,20))*np.maximum(sectors_n[:14][None,:],1e-12)
  arr=arr/arr.sum(axis=1,keepdims=True)
  n0=float(sectors_n[-1]);prior=np.column_stack([arr*(1-n0),np.full(len(dep_codes),n0)])
  yield period,prior,status


def monthly_reconciliation(root,annual,month_info,output,save=True):
 base=month_info[['period','dep_code','employed','employed_represented']].copy() if 'employed_represented' in month_info.columns else None
 if base is None:
  base=pd.read_csv(root/'inputs/departamentos.csv',usecols=['period','dep_code','employed','employed_represented'])
 nat=pd.read_csv(root/'inputs/12_composicion_nacional_unificada_1993_2026.csv')
 if len(nat)!=N_MONTHS*15 or len(base)!=N_MONTHS*33:raise ValueError('Panel nacional/departamental incompleto')
 if np.any(nat.sector_share<0) or not np.isfinite(nat.sector_share).all():raise ValueError('Invalid national shares')
 dep_codes=sorted(base.dep_code.unique());sect=SECTORS15
 pb=base.pivot(index='period',columns='dep_code',values='employed').reindex(columns=dep_codes)
 pr=base.pivot(index='period',columns='dep_code',values='employed_represented').reindex(columns=dep_codes)
 natwide=nat.pivot(index='period',columns='sector_code',values='sector_share').reindex(columns=sect)
 rows=[]; audit=[]
 anchor_map=annual[annual.sector_code.eq('A')].set_index(['dep_code','year']).anchor_status.to_dict()
 for period,prior,status in month_curve(base.assign(year=base.period.str[:4].astype(int)),annual,month_info,nat):
  employed=pb.loc[period].to_numpy(float);represented=pr.loc[period].to_numpy(float)
  ns=natwide.loc[period].to_numpy(float);ns=ns/ns.sum()
  totals=ns*employed.sum()
  x,n_iter=ipf(prior*employed[:,None],employed,totals)
  share=np.divide(x,employed[:,None],out=np.zeros_like(x),where=employed[:,None]>0)
  if not np.isfinite(share).all():raise AssertionError('Cuota no finita')
  audit.append({'period':period,'max_row_error_people':float(abs(x.sum(axis=1)-employed).max()),
         'max_national_sector_error_people':float(abs(x.sum(axis=0)-totals).max()),
         'max_prior_adjustment_pp':float((100*np.abs(prior-share)).max()),'iterations':n_iter,
         'geih_national_not_hard_constrained':True,
         'is_1993_2000_geih_assumed':bool(period<'2001-01')})
  for i,dep in enumerate(dep_codes):
   for j,s in enumerate(sect):
    anchor_status=(anchor_map.get((dep,int(period[:4])),'NO_DIRECT_DEPARTMENT_REFERENCE_PRE2015_OR_2026')
                   if s!='NO_INFO' else 'NO_INFO_NOT_AN_ECONOMIC_BRANCH')
    rows.append((period,dep,s,share[i,j],x[i,j],share[i,j]*represented[i],status,
                 'H11_RECONSTRUCTED_1993_2014' if period<'2015-01' else 'H11_NATIONAL_MONTHLY_POST2015',
                 anchor_status))
 ret=pd.DataFrame(rows,columns=['period','dep_code','sector_code','sector_share','employed_full_sector',
              'employed_represented_sector_proxy','territorial_prior_status','national_source_status','annual_anchor_status'])
 qa=pd.DataFrame(audit)
 if len(ret)!=N_MONTHS*33*15:raise AssertionError('No hay cobertura completa')
 if save:
  ret.to_csv(output/'16_matriz_mensual_1993_2026_EXPERIMENTAL.csv',index=False,float_format='%.12g',lineterminator='\n')
  qa.to_csv(output/'16_auditoria_margenes_mensuales.csv',index=False,lineterminator='\n')
 return ret,qa



def backcast_sensitivity(root,annual,output):
 """Hypothetical persistence sensitivity 2015→1993, NOT confidence bands.
 Reconcile on the frontier samples so variations are not attributed to different closures.
 """
 base=pd.read_csv(root/'inputs/departamentos.csv',usecols=['period','dep_code','employed'])
 nat=pd.read_csv(root/'inputs/12_composicion_nacional_unificada_1993_2026.csv')
 periods={'1993-01','1998-01','2001-01','2007-01','2014-12'}
 base['year']=base.period.str[:4].astype(int)
 deps=sorted(base.dep_code.unique())
 weights=base[base.period.isin(periods)].pivot(index='period',columns='dep_code',values='employed').reindex(columns=deps)
 nt=nat[nat.period.isin(periods)].pivot(index='period',columns='sector_code',values='sector_share').reindex(columns=SECTORS15)
 rows=[]
 for hl in [6.,12.,24.,None]:
  name='SIN_ATENUACION' if hl is None else f'SEMIVIDA_{int(hl)}_ANIOS'
  for period,prior,status in month_curve(base,annual,base,nat,half_life_years=hl):
   if period not in periods:continue
   r=weights.loc[period].to_numpy(float);sh=nt.loc[period].to_numpy(float)
   x,_=ipf(prior*r[:,None],r,sh/sh.sum()*r.sum())
   vals=np.divide(x,r[:,None],out=np.zeros_like(x),where=r[:,None]>0)
   for i,dep in enumerate(deps):
    for j,sec in enumerate(SECTORS15):
     rows.append((period,int(dep),sec,name,float(vals[i,j])))
 d=pd.DataFrame(rows,columns=['period','dep_code','sector_code','backcast_scenario','share'])
 baseline=d[d.backcast_scenario=='SEMIVIDA_12_ANIOS'][['period','dep_code','sector_code','share']].rename(columns={'share':'baseline_share'})
 d=d.merge(baseline,on=['period','dep_code','sector_code'],validate='many_to_one')
 d['abs_change_pp_vs_12years']=100*(d.share-d.baseline_share).abs()
 d.to_csv(output/'16_sensibilidad_retropolacion.csv',index=False,lineterminator='\n')
 resumen=d.groupby(['period','backcast_scenario'],as_index=False).agg(
   max_abs_change_pp=('abs_change_pp_vs_12years','max'),mean_abs_change_pp=('abs_change_pp_vs_12years','mean'))
 resumen.to_csv(output/'16_sensibilidad_retropolacion_resumen.csv',index=False,lineterminator='\n')
 return resumen

def annual_observation_audit(root,monthly,annual):
 # The observed shares refer to the employment classified in the GEIH.
 # The proxies are aggregated weighted by the represented employment per MONTH;
 # they are NOT confused with simple averages of twelve shares.
 m=monthly[monthly.sector_code!='NO_INFO'].copy();m['year']=m.period.str[:4].astype(int)
 m['pred_annual']=m.employed_represented_sector_proxy
 a=m.groupby(['dep_code','year','sector_code'],as_index=False).pred_annual.sum()
 a['pred_share']=a.pred_annual/a.groupby(['dep_code','year']).pred_annual.transform('sum')
 x=annual[['dep_code','year','sector_code','obs_share','share_model','share_anchored']]
 a=a.merge(x,on=['dep_code','year','sector_code'],how='inner',validate='one_to_one')
 a=a[a.obs_share.notna()].copy()
 a['error_abs_pp']=100*(a.pred_share-a.obs_share).abs()
 a['distortion_against_anchored_pp']=100*(a.pred_share-a.share_anchored).abs()
 return a


def main(root):
 root=Path(root);out=root/'outputs';out.mkdir(exist_ok=True)
 annual,labor=load_labor_features(root)
 features,observed,gdp_cols=training_panel(root,annual)
 oof=logo(observed,gdp_cols);scores_file,scores,bydep,alpha,alpha_grid=evaluate(oof,root)
 oof.to_csv(out/'16_original38_vs_37_logo.csv',index=False,lineterminator='\n')
 scores_file.to_csv(out/'16_validacion_pareada_celdas.csv',index=False,lineterminator='\n')
 scores.to_csv(out/'16_metricas_predictor.csv',index=False,lineterminator='\n')
 bydep.to_csv(out/'16_metricas_departamentos.csv',index=False,lineterminator='\n')
 eligible=scores[scores.test_protocol=='LOGO_2015_2024'].sort_values(['mae_pp','model'])
 chosen=str(eligible.iloc[0]['model'])
 # Never choose an estimator by comparing it against the reserved year 2025.
 candidate=annual_candidates(root,features,observed,gdp_cols,chosen,alpha)
 anchored=annual_target_table(root,candidate)
 anchored.to_csv(out/'16_candidatos_anuales_2015_2025.csv',index=False,lineterminator='\n')
 monthly,qa=monthly_reconciliation(root,anchored,labor,out)
 sens=backcast_sensitivity(root,anchored,out)
 # External evaluation BEFORE anchoring: not to be confused with fitting to references.
 bgre=pd.read_csv(root/'inputs/14_referencia_externa_Bogota_DANE_GEIH_2015_2024.csv')
 bgre=bgre.rename(columns={'group_code':'sector_code'})
 bgre['obs_share']=bgre.observed_share_pct/bgre.groupby('year').observed_share_pct.transform('sum')
 bgpre=anchored[anchored.dep_code.eq(11)].merge(bgre[['year','sector_code','obs_share']],
                 on=['year','sector_code'],suffixes=('','_ref'),validate='one_to_one')
 bgpre['abs_error_pp']=100*(bgpre.share_model-bgpre.obs_share_ref).abs()
 bgpre[['year','sector_code','share_model','obs_share_ref','abs_error_pp']].to_csv(
       out/'16_bogota_evaluacion_independiente_PRE_ANCLA.csv',index=False,
                lineterminator='\n')
 check=annual_observation_audit(root,monthly,anchored)
 check.to_csv(out/'16_auditoria_anclas_GEIH_anuales.csv',index=False,lineterminator='\n')
 flags=check.groupby('year',as_index=False).agg(mae_pp=('error_abs_pp','mean'),max_pp=('error_abs_pp','max'))
 flags.to_csv(out/'16_error_anual_geih.csv',index=False,lineterminator='\n')
 feature_info=pd.DataFrame({'feature':predictor_feature_names(gdp_cols,True),
                            'original38_component':[x.startswith('original_') for x in predictor_feature_names(gdp_cols,True)]})
 feature_info.to_csv(out/'16_inventario_variables.csv',index=False,lineterminator='\n')
 quality={'checkpoint':'ICML_2_2_18','status':'EXPERIMENTAL_NOT_CANONICAL',
  'trained_labels':'2015_2024','holdout_labels':'2025_not_used_in_any_fit',
  'chosen_by':'LOGO_2015_2024_only_not_nested_model_selection','chosen_model':chosen,
  'ensemble_alpha_xgb':alpha,'predefined_alpha_grid_logo_mae':alpha_grid,
  'original38_recovered':True,'original38_model_exact_reproduction':False,
  'informality_source':'ICML_original_vintage_labor_panel_2007_2025_NOT_AS_OF',
  'n_official_reference_departments':23,'n_external_bogota_anchor_years':10,
  'n_territories_without_any_observed_annual_sector_anchor':9,
  'n_months':N_MONTHS,'n_sectors':15,'n_departments':33,
  'max_monthly_dept_closure_people':float(qa.max_row_error_people.max()),
  'max_monthly_national_closure_people':float(qa.max_national_sector_error_people.max()),
  'max_adjustment_vs_monthly_prior_pp':float(qa.max_prior_adjustment_pp.max()),
  'max_backcast_sensitivity_pp_vs_12year_reference':float(sens.max_abs_change_pp.max()),
  'geih_annual_mae_pp':float(check.error_abs_pp.mean()),'geih_annual_max_pp':float(check.error_abs_pp.max()),
  'bogota_geih_annual_mae_pp':float(check[check.dep_code.eq(11)].error_abs_pp.mean()),
  'bogota_model_external_pre_anchor_mae_pp':float(bgpre.abs_error_pp.mean()),
  'official_annual_exactly_imposed':False,'national_complete_monthly_exactly_constrained':True,
  'geih_represented_national_monthly_not_forced':True,
  'monthlyized_1993_2014_department_sector_with_assumed_trends':True,
  'monthlyizing_2015_2025_assumes_within_year_national_cycle':True,
  '2026_no_gdp_2025_annual_profile_carried_from_2025':True,
  'pre2001_represented_national_unreconciled':True,
  'can_publish':False,
  'critical_limitations':['Anclas 23 departamentos 2015-2025 de la extracción original sin cotejo final con anexos DANE',
   'Retroestimación territorial 1993-2014 no identificada directamente',
   '1980s/1990s sin anclas departamentales sectoriales observadas',
   'PIB 2015-2024 vintage retrospectivo, no backtest real time',
   'No se permite cierre exacto simultáneo de márgenes nacionales completos con cuotas anuales GEIH incompatibles',
   'El empleo de 2026 utiliza perfil territorial de 2025; 2026 no presenta PIB 2025 en insumos',
   'La informalidad original 2007-2025 se usa como covariable, no como actualización canónica'],
  'scores':scores.to_dict('records')}
 (out/'16_puerta_calidad.json').write_text(json.dumps(quality,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 inputs={p.name:sha(p) for p in sorted((root/'inputs').glob('*.csv'))}
 outputs={p.name:sha(p) for p in sorted(out.glob('*')) if p.is_file() and p.name!='16_manifest_hashes.json'}
 (out/'16_manifest_hashes.json').write_text(json.dumps({'inputs_sha256':inputs,'outputs_sha256':outputs},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 print(json.dumps({'chosen':chosen,'scores':quality['scores'],'monthly_rows':len(monthly),
   'max_national_error':quality['max_monthly_national_closure_people'],
   'official_annual_error_mean_pp':quality['geih_annual_mae_pp']},ensure_ascii=False,indent=2))
 return quality

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));arg=ap.parse_args()
 main(arg.root)
