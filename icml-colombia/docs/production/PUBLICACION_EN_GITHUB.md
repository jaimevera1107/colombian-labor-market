# Publicación en GitHub: primer push y respaldo mensual

El repositorio contiene todo (código, datos, referencias, entrega vigente y sus gráficos), unos 650 MB, y el mayor
pesa 35 MB. No usa Git LFS, así que cualquiera que lo descargue, incluso con *Download ZIP*, recibe todo.

## Reemplazar el contenido de <https://github.com/jaimevera1107/colombian-labor-market>

El repositorio ya existe y su contenido se va a **reemplazar por completo**. Un push normal no sirve, porque la historia
del repositorio actual y la de este no comparten nada; hace falta un push forzado, que sobrescribe la rama.

### Antes de empezar

1. **Respaldar lo que hay ahora.** El push forzado es irreversible desde GitHub:

   ```
   git clone --mirror https://github.com/jaimevera1107/colombian-labor-market.git respaldo-colombian-labor-market.git
   ```

   Guarde esa carpeta (conserva todas las ramas, etiquetas y la historia).
2. **Revisar la visibilidad** en *Settings → General → Danger zone*. Este repositorio incluye datos del DANE procesados,
   las referencias de validación y las entregas. Si el repositorio es público, todo quedará público.
3. **Ver cuál es su rama principal:**

   ```
   git ls-remote --symref https://github.com/jaimevera1107/colombian-labor-market.git HEAD
   ```

   Si responde `refs/heads/main`, siga tal cual; si responde `refs/heads/master`, use `main:master` en el push.

### Pasos

```
git clone ICML_repo.bundle ICML
cd ICML
git config user.name  "Su nombre"
git config user.email "su-correo@ejemplo.com"
git commit --amend --reset-author --no-edit
git remote set-url origin https://github.com/jaimevera1107/colombian-labor-market.git
git push --force origin main
git push origin v2.3.0.dev0
```

(Si la rama principal es `master`: `git push --force origin main:master`.) Si el push de unos 160 MB comprimidos se
corta, use SSH o aumente el búfer: `git config http.postBuffer 524288000`.

### Después

* **Otras ramas y etiquetas** del repositorio anterior siguen existiendo. Véalas con
  `git ls-remote --heads --tags origin` y bórrelas en GitHub si no las quiere (`git push origin --delete <nombre>`).
* **Los commits antiguos** pueden seguir siendo accesibles por su hash durante un tiempo. Para eliminarlos de verdad, la
  alternativa es borrar el repositorio y crearlo de nuevo con el mismo nombre (se pierden estrellas, incidencias y
  bifurcaciones).
* En la pestaña *Actions*, comprobar que el flujo `tests` termina en verde (unos 15 minutos).

## Comprobar una copia

Desde la raíz de cualquier copia: `python icml-colombia/tools/release/verify_checkout.py`. Compara cada archivo con
`SHA256SUMS` y dice si falta o cambió alguno.

## Respaldo mensual

Después de recalcular y verificar la entrega:

```
python icml-colombia/tools/release/verify_checkout.py --escribir
git add -A
git commit -m "Entrega AAAA-MM"
git push
```

Las entregas anteriores no se borran: la última es la referencia del siguiente recálculo anclado.

## Licencia

MIT (archivo `LICENSE`, también en `icml-colombia/LICENSE` y en el campo `license` de `pyproject.toml`).
