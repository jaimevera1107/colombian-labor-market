"""H15 ICML: benchmark sectorial espacial + espacial-temporal y candidatos 33 territorios.

No deserializa modelos ajenos ni modifica vintages previos.

Original: 14 XGBoost independientes, datos de 14 ramas del proyecto ICML del autor.
Reentrenamiento explícito, NUNCA se llama reproducción completa del vector original
(urbana, informalidad, empalmes y donantes no auditados en todo 2015-2025).
"""
from __future__ import annotations
import argparse, hashlib, json, sys, platform, importlib.metadata
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor
from .hito4_reference import load_data, SECTORS, GDP_GROUPS, _norm, clr, inv_clr

MAP={"D+E":"D_E","M+N":"M_N","O+P+Q":"O_P_Q","R+S+T+U":"R_S_T_U"}
MODELS=['media_otros_departamentos','ridge_clr_pib_rezagado','extratrees_clr_pib_rezagado','xgb_14_original_aprox_pib_rezagado']
KEY=['department','year','sector_code']


def make_estimator(name,trees=160):
    if name=='ridge_clr_pib_rezagado':
        return make_pipeline(StandardScaler(),Ridge(alpha=30)),True
    if name=='extratrees_clr_pib_rezagado':
        return ExtraTreesRegressor(n_estimators=110,min_samples_leaf=3,max_features=0.85,random_state=2026,n_jobs=1),True
    if name=='xgb_14_original_aprox_pib_rezagado':
        base=XGBRegressor(n_estimators=trees,max_depth=4,learning_rate=.05,subsample=.8,
            colsample_bytree=.8,random_state=42,n_jobs=1,tree_method='hist',objective='reg:squarederror')
        return make_pipeline(StandardScaler(),MultiOutputRegressor(base,n_jobs=1)),False
    raise ValueError(name)


def clamp_simplex(pred):
    x=np.asarray(pred,float)
    if x.ndim!=2 or x.shape[1]!=len(SECTORS) or not np.isfinite(x).all():
        raise ValueError('Salidas no finitas o dimensionalidad incorrecta')
    x=np.maximum(x,1e-10)
    return x/x.sum(axis=1,keepdims=True)


def fit_predict(model, train, test, trees=160):
    estimator,using_clr=make_estimator(model,trees)
    X=np.stack([a['features_gdp'] for a in train]); y=np.stack([a['y'] for a in train]);
    Xt=np.stack([a['features_gdp'] for a in test])
    estimator.fit(X,clr(y) if using_clr else y)
    pred=estimator.predict(Xt)
    return clamp_simplex(inv_clr(pred) if using_clr else pred)


def benchmark(records,trees=160):
    all_deps=sorted({r['department'] for r in records});assert len(all_deps)==23
    oof=[]
    for i,held in enumerate(all_deps,1):
        train=[r for r in records if r['department']!=held and r['year']<=2024]
        te=[r for r in records if r['department']==held]
        assert len(train)==22*10 and len(te)==11
        assert not any(r['department']==held or r['year']>=2025 for r in train)
        for m in MODELS:
            if m=='media_otros_departamentos':
                avg_by_year={y:np.mean([a['y'] for a in train if a['year']==y],axis=0) for y in range(2015,2025)}
                pred=clamp_simplex(np.array([avg_by_year[min(t['year'],2024)] for t in te]))
            else:pred=fit_predict(m,train,te,trees)
            for t,row in zip(te,pred):
                for j,s in enumerate(SECTORS):
                    oof.append({'experiment':'LOGO_2015_2024' if t['year']<=2024 else 'LOGO_PLUS_FUTURE_2025',
                      'department':held,'year':t['year'],'sector_code':MAP.get(s,s),'model':m,
                      'observed_share':float(t['y'][j]),'predicted_share':float(row[j])})
        print(f'fold {i:02d}/{len(all_deps)} {held}',flush=True)
    out=pd.DataFrame(oof)
    if len(out)!=len(MODELS)*23*11*14:raise AssertionError('OOF cobertura incompleta')
    return out


def features_all_33(root:Path):
    pop=pd.read_csv(root/'inputs/population_projections.csv');gdp=pd.read_csv(root/'inputs/gdp_groups_2005_2024.csv')
    pop['dep_key']=pop.dep_name.map(_norm);pop['area_key']=pop.area_type.str.lower().str.strip();gdp['dep_key']=gdp.department.map(_norm)
    # Mapeo explícito y único de San Andrés entre nomenclaturas DANE distintas.
    gdp['dep_key']=gdp['dep_key'].replace({'sanandresprovidenciaysantacatalina(archipielago)':'archipielagodesanandres'})
    popv=pop.pivot(index=['dep_key','year'],columns='area_key',values='population')
    gdv=gdp.pivot(index=['dep_key','year'],columns='gdp_code',values='value_billion_cop')
    names=pop[pop.area_key=='total'][['dep_key','dep_name','dep_code']].drop_duplicates('dep_key')
    ret=[]
    for r in names.itertuples(index=False):
        for year in range(2015,2026):
            key=(r.dep_key,year);gkey=(r.dep_key,year-1)
            if key not in popv.index or gkey not in gdv.index:raise ValueError(f'Cobertura faltante {r.dep_name}/{year}')
            p=popv.loc[key];g=gdv.loc[gkey]; gp=g[GDP_GROUPS].to_numpy(float)
            if not np.isfinite(gp).all() or gp.sum()<=0 or np.any(gp<0):raise ValueError('PIB inválido')
            pt=float(p['total']);cab=float(p['cabecera']);
            x=np.array([float(year),np.log(pt),cab/pt,np.log(gp.sum()*1e9/pt),*(gp/gp.sum())])
            if len(x)!=16:raise AssertionError('16 features')
            ret.append({'department':r.dep_name,'dep_code':int(r.dep_code),'year':year,
                        'features_gdp':x,'feature_gdp_reference_year':year-1})
    if len(ret)!=33*11:raise ValueError(f'Cobertura no es 33 x 11: {len(ret)}')
    return ret


def predict_33(records,allfeatures,trees=160):
    train=[r for r in records if r['year']<=2024]
    observed={(_norm(r['department']),r['year']):r['y'] for r in records}
    # Train 2015-2024 only: no label 2025 to fit parameters, including inference 2025.
    estimators={}
    X=np.stack([r['features_gdp'] for r in train]); y=np.stack([r['y'] for r in train]);Xt=np.stack([r['features_gdp'] for r in allfeatures])
    results=[]
    for model in MODELS:
        if model==MODELS[0]:
            byyear={yr:np.mean([r['y'] for r in train if r['year']==yr],axis=0) for yr in range(2015,2025)}
            pred=clamp_simplex(np.array([byyear[min(f['year'],2024)] for f in allfeatures]))
        else:
            est,using_clr=make_estimator(model,trees)
            est.fit(X,clr(y) if using_clr else y)
            z=est.predict(Xt)
            pred=clamp_simplex(inv_clr(z) if using_clr else z)
        for f,share in zip(allfeatures,pred):
            key=(_norm(f['department']),f['year']);official=observed.get(key)
            for j,s in enumerate(SECTORS):
                results.append({'department':f['department'],'dep_code':f['dep_code'],'year':f['year'],
                  'gdp_reference_year':f['feature_gdp_reference_year'],'sector_code':MAP.get(s,s), 'model':model,
                  'predicted_share':float(share[j]),'observed_reference_share':float(official[j]) if official is not None else np.nan,
                  'data_status':'DANE_OFFICIAL_ANNUAL_PRESENT' if official is not None else 'NO_DEPARTMENT_SECTOR_REFERENCE',
                  'inference_status':'TRAINED_THROUGH_2024_2025_HELD_OUT' if f['year']==2025 else 'FULL_TRAIN_NOT_OUT_OF_SAMPLE',
                  'canonical':False})
    return pd.DataFrame(results)


def scores(oof, ref):
    ref=ref.copy(); ref['experiment']=np.where(ref.year<=2024,'LOGO_2015_2024','LOGO_PLUS_FUTURE_2025')
    ref=ref.rename(columns={'estimate_share':'predicted_share','official_share':'observed_share'})
    ref=ref[['experiment','department','year','sector_code','model','observed_share','predicted_share']]
    combined=pd.concat([oof,ref],ignore_index=True)
    combined['abs_error_pp']=100*np.abs(combined.predicted_share-combined.observed_share)
    z=combined.groupby(['experiment','model'],as_index=False).agg(
        mae_pp=('abs_error_pp','mean'),p90_error_pp=('abs_error_pp',lambda a:float(np.quantile(a,.9))),
        worst_error_pp=('abs_error_pp','max'),n_cells=('abs_error_pp','size'))
    dep=combined.groupby(['experiment','model','department'],as_index=False).agg(mae_pp=('abs_error_pp','mean'))
    worst=dep.groupby(['experiment','model'],as_index=False).agg(worst_department_mae_pp=('mae_pp','max'))
    z=z.merge(worst,on=['experiment','model'])
    branches=combined.groupby(['experiment','model','sector_code'],as_index=False).agg(mae_pp=('abs_error_pp','mean'))
    # compare paired MAE at department, year; scores per heldout department
    p=dep.pivot(index=['experiment','department'],columns='model',values='mae_pp').reset_index()
    return combined,z,dep,branches,p



def validate_bogota(pred33, root):
    """Comprobación verdaderamente externa: Bogotá NO figura en los 23 fit/LOGO.

    Su referencia H14 está redondeada a décimas, por lo que se normaliza por año
    dentro de las 14 ramas. No se incorpora al entrenamiento ni se imputa a 2025.
    """
    ref=pd.read_csv(root/'inputs/14_referencia_externa_Bogota_DANE_GEIH_2015_2024.csv')
    ref['observed_share']=ref.observed_share_pct/ref.groupby('year').observed_share_pct.transform('sum')
    pred=pred33[(pred33.dep_code==11) & pred33.year.between(2015,2024)]
    joined=pred.merge(ref,left_on=['year','sector_code'],right_on=['year','group_code'],validate='many_to_one')
    if len(joined)!=4*10*14:raise AssertionError('Bogotá: faltan ramas/años')
    joined['abs_error_pp']=(joined.predicted_share-joined.observed_share).abs()*100
    return joined[['model','year','sector_code','observed_share','predicted_share','abs_error_pp']],joined.groupby('model',as_index=False).agg(mae_pp=('abs_error_pp','mean'),max_error_pp=('abs_error_pp','max'),n=('abs_error_pp','size'))


def audit_support(records, allfeatures):
    """Distancias de soporte: rasgo diagnóstico, NO probabilidad ni error esperado."""
    from scipy.spatial.distance import cdist
    out=[]
    for yr in (2024,2025):
        tr=[r for r in allfeatures if yr==r['year'] and _norm(r['department']) in {_norm(t['department']) for t in records}]
        unseen=[r for r in allfeatures if yr==r['year'] and _norm(r['department']) not in {_norm(t['department']) for t in records}]
        assert len(tr)==23 and len(unseen)==10
        tr_x=np.stack([r['features_gdp'] for r in tr]); te_x=np.stack([r['features_gdp'] for r in unseen]);
        scaler=StandardScaler().fit(tr_x); a=scaler.transform(tr_x);b=scaler.transform(te_x)
        d=cdist(a,a);np.fill_diagonal(d,np.inf);th=float(np.percentile(d.min(axis=1),95))
        nearest=cdist(b,a);scores=nearest.min(axis=1)
        for r,di,idx in zip(unseen,scores,nearest.argmin(axis=1)):
            out.append({'year':yr,'department':r['department'],'dep_code':r['dep_code'],
              'nearest_observed_department':tr[idx]['department'],'standardized_distance':float(di),
              'train_loo_p95_distance':th,'out_of_support':bool(di>th),
              'interpretation':'HEURISTIC_GEOMETRIC_DISTANCE_NOT_CONFIDENCE_INTERVAL'})
    return pd.DataFrame(out)


def model_disagreement(pred33):
    """Dispersión de 3 familias sobre territorios sin anclas: sensibilidad, NO intervalos."""
    d=pred33[(pred33.model.isin(MODELS[1:])) & (pred33.data_status=='NO_DEPARTMENT_SECTOR_REFERENCE')]
    a=d.groupby(['year','dep_code','department','sector_code'],as_index=False).agg(
      min_share=('predicted_share','min'),max_share=('predicted_share','max'),
      mean_share=('predicted_share','mean'),n_models=('model','nunique'))
    a['spread_pp']=100*(a.max_share-a.min_share)
    a['uncertainty_type']='SENSITIVITY_ACROSS_THREE_MODEL_FAMILIES_NOT_CONFIDENCE_INTERVAL'
    assert a.n_models.eq(3).all() and len(a)==10*11*14
    return a


def paired_bootstrap(paired):
    """Descriptivo por clúster departamento, evitando falsa independencia de 14 ramas."""
    rng=np.random.default_rng(2026);res=[]
    competitors=['xgb_14_original_aprox_pib_rezagado','extratrees_clr_pib_rezagado','CONJUNTO:RURAL_PROXY_MODERATE','CONJUNTO:NEUTRAL_NATIONAL']
    for exp,g in paired.groupby('experiment'):
        g=g.sort_values('department')
        a=g['ridge_clr_pib_rezagado'].to_numpy(float)
        for m in competitors:
            diff=g[m].to_numpy(float)-a
            ids=rng.integers(0,len(diff),size=(2000,len(diff)))
            draws=diff[ids].mean(axis=1)
            res.append({'experiment':exp,'reference':m,'candidate':'ridge_clr_pib_rezagado',
              'mean_improvement_pp':float(diff.mean()),'bootstrap_025_pp':float(np.quantile(draws,.025)),
              'bootstrap_975_pp':float(np.quantile(draws,.975)),
              'n_department_clusters':len(diff),'resamples':2000,
              'note':'DESCRIPTIVE_CLUSTER_BOOTSTRAP_NOT_GENERALIZATION_TO_UNOBSERVED_DEPARTMENTS'})
    return pd.DataFrame(res)

def diagnose_anchor_feasibility(pred33,root):
    # Diagnostic only. Do not impose full-ICML sector margins on annual DANE GEIH proportions.
    d=pd.read_csv(root/'inputs/12_pesos_anuales_completo_H12.csv')
    weights=d.groupby(['year','dep_code','sector_code'],as_index=False)['employed_full_sector'].sum()
    den=weights.groupby(['year','dep_code'],as_index=False)['employed_full_sector'].sum().rename(columns={'employed_full_sector':'employed_full_annual'})
    # Classified only: 14 sectors. Observed official shares denominator = 14 classified sectors.
    weights14=weights[weights.sector_code!='NO_INFO']
    national=weights14.groupby(['year','sector_code'],as_index=False)['employed_full_sector'].sum()
    national['target_share_classified']=national.employed_full_sector/national.groupby('year').employed_full_sector.transform('sum')
    ann=den.merge(pred33[pred33.model==MODELS[1]][['dep_code','year','sector_code','predicted_share','observed_reference_share','data_status']],on=['dep_code','year'])
    ann=ann[ann.sector_code!='NO_INFO'].copy()
    # The employment totals are complete-universe; this is a hypothetical audit not a valid forced DANE restriction.
    ann['weighted_obs']=np.where(ann.data_status=='DANE_OFFICIAL_ANNUAL_PRESENT',ann.employed_full_annual*ann.observed_reference_share,0.)
    observed=ann.groupby(['year','sector_code'],as_index=False).weighted_obs.sum()
    total=den.groupby('year').employed_full_annual.sum()
    observed=observed.merge(total,on='year').merge(national[['year','sector_code','target_share_classified']],on=['year','sector_code'])
    observed['observed_fraction_total']=observed.weighted_obs/observed.employed_full_annual
    observed['remaining_margin_fraction']=observed.target_share_classified-observed.observed_fraction_total
    observed['hard_anchors_feasible_if_same_universe']=observed.remaining_margin_fraction>=-1e-10
    observed['warning']='DIAGNOSTIC_ONLY_DIFFERENT_UNIVERSES_AND_SECTOR_CLASSIFICATION'
    return observed


def sha256(f):
    h=hashlib.sha256()
    with open(f,'rb') as z:
      for b in iter(lambda:z.read(2**20),b''):h.update(b)
    return h.hexdigest()


def run(root:Path,trees:int=160):
    inp=root/'inputs';out=root/'outputs';out.mkdir(exist_ok=True,parents=True)
    records,meta=load_data(inp/'official_sectors_2015_2025.csv',inp/'population_projections.csv',inp/'gdp_groups_2005_2024.csv',max_year=2025,gdp_lag_years=1)
    assert len(records)==253 and meta['territories']==23
    oof=benchmark(records,trees)
    ref=pd.read_csv(inp/'comparacion_celdas_h13_vs_dane.csv')
    assert len(ref)==17710
    c,s,dep,branch,paired=scores(oof,ref)
    allf=features_all_33(root)
    p33=predict_33(records,allf,trees)
    disagreement=model_disagreement(p33)
    paired_stats=paired_bootstrap(paired)
    bg,bgsummary=validate_bogota(p33,root)
    support=audit_support(records,allf)
    # Complete grid, all models and departments. Label 2025 withheld for training in every model.
    assert len(p33)==4*33*11*14
    assert np.allclose(p33.groupby(['model','dep_code','year']).predicted_share.sum().to_numpy(),1.,atol=1e-10)
    assert not p33.duplicated(['model','dep_code','year','sector_code']).any()
    if (inp/'12_pesos_anuales_completo_H12.csv').is_file():
        diag=diagnose_anchor_feasibility(p33,root)
        diag.to_csv(out/'15_diagnostico_factibilidad_margenes.csv',index=False)
    files={'15_predicciones_oof.csv':oof,'15_comparacion_pareada_h13.csv':c,
           '15_metricas_modelos.csv':s,'15_error_por_departamento.csv':dep,
           '15_error_por_rama.csv':branch,'15_pareos_por_departamento.csv':paired,
           '15_candidatos_anuales_33_territorios.csv':p33,
           '15_bogota_contraste_externo.csv':bg,
           '15_bogota_metricas.csv':bgsummary,
           '15_extrapolacion_fuera_soporte.csv':support,
           '15_sensibilidad_modelos_sin_anclas.csv':disagreement,
           '15_diferencias_pareadas_bootstrap.csv':paired_stats}
    for fn,d in files.items():d.to_csv(out/fn,index=False,float_format='%.12g')
    gate={'status':'BLOCKED_FOR_CANONICAL_PUBLICATION',
      'reasons':['NO_FULL_ORIGINAL_38_FEATURES_AND_URBAN_DONOR_PIPELINE',
                 'DIFFERENT_UNIVERSES_DANE_ANNUAL_VS_ICML_FULL',
                 'OUT_OF_SUPPORT_UNLABELED_TERRITORIES',
                 'GEIH_TERRITORIAL_GEOGRAPHICAL_COVERAGE_NOT_EQUAL_TO_33',
                 'MONTHLY_RECONSTRUCTION_AND_NATIONAL_RECONCILIATION_NOT_VALIDATED'],
      'annual_benchmark_usable':True,'h11_or_prior_vintages_modified':False}
    (out/'15_puerta_calidad.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2),encoding='utf-8')
    comparison={'best_spatial':s[s.experiment=='LOGO_2015_2024'].sort_values('mae_pp').iloc[0][['model','mae_pp']].to_dict(),
                'best_future':s[s.experiment=='LOGO_PLUS_FUTURE_2025'].sort_values('mae_pp').iloc[0][['model','mae_pp']].to_dict()}
    manifest={'label':'H15_PREDICTOR_RECUPERADO_EXPERIMENTAL','canonical':False,'trees':trees,
      'source':'ICML_Original_Produccion_Integral reports/hito3 + data_aux + H13 comparisons',
      'n_observed_department_years':253,'cv_spatial_oof':230,'cv_spatiotemporal_oof':23,
      'department_count_predicted':33,'national_hard_margin_forced':False,'external_bogota_validation_only':True,
      'models':MODELS,'not_reproduced':'38 original features / trained joblib / historical urban donors, informality & whole legacy monthly pipeline',
      'label_convention':'14 DANE sectors conditional on classified employed; NO_INFO remains outside this model',
      'validation':'All OOF training excludes held-out department (2015-2025) and any 2025 label. 2025 uses year-2024 GDP retrospective',
      'time_safety':'GDP lag 1 does not prove as-of vintage available; population projections may include revisions',
      'environment':{'python':platform.python_version(),**{k:importlib.metadata.version(k) for k in ['numpy','pandas','scipy','scikit-learn','xgboost']}},
      'data_hashes':{p.name:sha256(p) for p in sorted(inp.iterdir()) if p.is_file()},
      'results_hashes':{p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='15_manifiesto.json' and p.suffix in {'.csv','.json'}},'comparison':comparison}
    (out/'15_manifiesto.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(s.sort_values(['experiment','mae_pp']).to_string(index=False),flush=True)
    print('Bogota externo:',bgsummary.sort_values('mae_pp').to_string(index=False),flush=True)
    print('Fuera de soporte 2024/2025:',support.groupby('year').out_of_support.sum().to_dict(),flush=True)
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--trees',type=int,default=160)
    q=p.parse_args();run(q.root,q.trees)

if __name__=='__main__':main()
