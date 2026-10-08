"""Protected editorial administration. All POSTs use the existing CSRF guard."""
import base64
import time
import uuid
from PIL import Image
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from editorial import (Editorial, ANIMATIONS, PLACEMENTS, BLOCK_KINDS, BUSINESS_TZ,
                       poster_form, choice, integer, string, schedule, local_date)
from uploads import prepare_image


def register_editorial(app,catalog,storage):
    editor=Editorial(catalog)
    app.extensions['editorial']=editor
    bp=Blueprint('editorial',__name__)
    app.jinja_env.globals.update(editorial_animations=ANIMATIONS, editorial_placements=PLACEMENTS,
                                block_kinds=BLOCK_KINDS,local_date=local_date)

    def get(pid):
        row=editor.get(pid)
        if not row: abort(404)
        return row

    def fields(existing=None):
        return poster_form(request.form,catalog.list(),existing)

    def image_values(file,preview=False):
        stream=prepare_image(file)
        with Image.open(stream) as image:
            width,height=image.size
            fmt=image.format.lower()
        stream.seek(0)
        if preview:
            return dict(preview_image='data:image/'+fmt+';base64,'+base64.b64encode(stream.read()).decode(),image_width=width,image_height=height)
        public_id='tentarte/editorial/'+uuid.uuid4().hex
        catalog.queue_cleanup(public_id,delay=86400)
        # An upload timeout can still complete remotely; retain its delayed cleanup intent.
        try: url=storage.upload(stream,public_id)
        except Exception: abort(502,'No se pudo subir la imagen. El cartel anterior se conserva; reintentá.')
        return dict(image=url,image_id=public_id,image_width=width,image_height=height)

    @bp.get('/admin/posters')
    def listing():
        return render_template('posters/list.html',posters=editor.posters())

    @bp.get('/admin/posters/new')
    @bp.get('/admin/posters/<int:pid>')
    def edit(pid=None):
        return render_template('posters/edit.html',poster=get(pid) if pid else None,products=catalog.list(),campaigns=editor.campaign_list())

    @bp.post('/admin/posters')
    @bp.post('/admin/posters/<int:pid>')
    def save(pid=None):
        existing=get(pid) if pid else None
        upload=None
        try:
            values=fields(existing)
            revision=integer(request.form.get('revision',1),1,2147483647)
            if existing and existing['revision']!=revision: raise ValueError('El cartel cambió. Recargá antes de guardar.')
            file=request.files.get('image')
            if file and file.filename:
                upload=image_values(file)
                values.update(upload)
            pid=editor.save(pid,values,revision)
        except ValueError as error:
            if upload: catalog.queue_cleanup(upload['image_id']); catalog.clean(storage)
            abort(400,str(error))
        except Exception:
            if upload: catalog.queue_cleanup(upload['image_id']); catalog.clean(storage)
            raise
        catalog.clean(storage)
        flash('Cartel guardado.')
        return redirect(url_for('editorial.edit',pid=pid))

    @bp.post('/admin/posters/<int:pid>/<action>')
    def action(pid,action):
        try:
            if action=='delete' and request.form.get('confirm')!='delete': raise ValueError('Confirmá la eliminación del cartel.')
            result=editor.action(pid,action,integer(request.form.get('revision'),1,2147483647))
        except ValueError as error: abort(400,str(error))
        catalog.clean(storage)
        flash('Cartel duplicado como borrador.' if action=='duplicate' else 'Cartel actualizado.')
        return redirect(url_for('editorial.edit',pid=result) if action=='duplicate' else url_for('editorial.listing'))

    @bp.post('/admin/posters/preview')
    def preview():
        try:
            pid=integer(request.form.get('poster_id'),1,2147483647) if request.form.get('poster_id') else None
            existing=get(pid) if pid else None
            values=dict(existing or {}) | fields(existing)
            values['href']=values['link']
            file=request.files.get('image')
            if file and file.filename: values.update(image_values(file,preview=True))
        except ValueError as error: abort(400,str(error))
        return render_template('posters/preview.html',poster=values)

    @bp.get('/admin/composition')
    def composition():
        return render_template('posters/composition.html',blocks=editor.blocks(),posters=editor.posters(),revision=catalog.settings().get('home_revision','1'))

    @bp.post('/admin/composition')
    def save_composition():
        try:
            kinds=request.form.getlist('kind')
            names=('target','title','body','active')
            columns={name:request.form.getlist(name) for name in names}
            if any(len(v)!=len(kinds) for v in columns.values()): raise ValueError('El formulario está incompleto.')
            rows=[]
            for pos,kind in enumerate(kinds):
                choice(kind,BLOCK_KINDS,'el tipo de bloque')
                target=string(columns['target'][pos],100)
                if kind=='poster_group': choice(target,PLACEMENTS,'el grupo de carteles')
                elif kind=='poster': integer(target,1,2147483647)
                else: target=''
                rows.append(dict(kind=kind,target=target,title=string(columns['title'][pos],150,kind=='text'),body=string(columns['body'][pos],1000),active=columns['active'][pos]=='1',position=pos))
            editor.save_blocks(rows,integer(request.form.get('revision'),1,2147483647))
        except ValueError as error: abort(400,str(error))
        flash('Composición guardada.')
        return redirect(url_for('editorial.composition'))

    @bp.get('/admin/campaigns')
    def campaign_list():
        return render_template('posters/campaigns.html',campaigns=editor.campaign_list())

    @bp.get('/admin/campaigns/new')
    @bp.get('/admin/campaigns/<int:cid>')
    def campaign_edit(cid=None):
        campaign=next((c for c in editor.campaign_list() if c['id']==cid),None)
        if cid and not campaign: abort(404)
        return render_template('posters/campaign_edit.html',campaign=campaign,posters=[p for p in editor.posters() if p['campaign_id']==cid] if cid else [])

    @bp.post('/admin/campaigns')
    @bp.post('/admin/campaigns/<int:cid>')
    def campaign_save(cid=None):
        try:
            values=dict(name=string(request.form.get('name'),150,True),active=request.form.get('active')=='on',priority=integer(request.form.get('priority',0)),**schedule(request.form))
            cid=editor.save_campaign(cid,values,integer(request.form.get('revision',1),1,2147483647))
        except ValueError as error: abort(400,str(error))
        flash('Campaña guardada. Asociá sus carteles desde la edición de cada uno.')
        return redirect(url_for('editorial.campaign_edit',cid=cid))

    app.register_blueprint(bp)
    return editor
