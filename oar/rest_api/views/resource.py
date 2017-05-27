# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
oar.rest_api.views.resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define resources api interaction

"""
from __future__ import division

from flask import url_for, g
from oar.lib import (db, Resource)

from . import Blueprint
from ..utils import Arg

import json

app = Blueprint('resources', __name__, url_prefix="/resources")


@app.route('/', methods=['GET'])
@app.route('/<any(details, full):detailed>', methods=['GET'])
@app.route('/nodes/<string:network_address>', methods=['GET'])
@app.args({'offset': Arg(int, default=0),
           'limit': Arg(int)})
def index(offset, limit, network_address=None, detailed=False):
    """Replie a comment to the post.

    :param offset: post's unique id
    :type offset: int

    :form email: author email address
    :form body: comment body
    :reqheader Accept: the response content type depends on
                      :mailheader:`Accept` header
    :status 302: and then redirects to :http:get:`/resources/(int:resource_id)`
    :status 400: when form parameters are missing
    """
    query = db.queries.get_resources(network_address, detailed)
    page = query.paginate(offset, limit)
    g.data['total'] = page.total
    g.data['links'] = page.links
    g.data['offset'] = offset
    g.data['items'] = []
    for item in page:
        attach_links(item)
        g.data['items'].append(item)


@app.route('/<int:resource_id>', methods=['GET'])
def show(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    g.data.update(resource.asdict())
    attach_links(g.data)


@app.route('/<int:resource_id>/jobs', methods=['GET'])
@app.args({'offset': Arg(int, default=0), 'limit': Arg(int)})
def jobs(offset, limit, resource_id=None):

    query = db.queries.get_jobs_resource(resource_id)
    page = query.paginate(offset, limit)
    g.data['total'] = page.total
    g.data['links'] = page.links
    g.data['offset'] = offset
    g.data['items'] = []
    for item in page:
        attach_job(item)
        g.data['items'].append(item)

def attach_links(resource):
    rel_map = (
        ("node", "member", "index"),
        ("show", "self", "show"),
        ("jobs", "collection", "jobs"),
    )
    links = []
    for title, rel, endpoint in rel_map:
        if title == "node" and "network_address" in resource:
            url = url_for('%s.%s' % (app.name, endpoint),
                          network_address=resource['network_address'])
            links.append({'rel': rel, 'href': url, 'title': title})
        elif title != "node" and "id" in resource:
            url = url_for('%s.%s' % (app.name, endpoint),
                          resource_id=resource['id'])
            links.append({'rel': rel, 'href': url, 'title': title})
    resource['links'] = links

def attach_job(job):
    rel_map = (
        ("show", "self", "show"),
        ("nodes", "collection", "nodes"),
        ("resources", "collection", "resources"),
    )
    job['links'] = []
    for title, rel, endpoint in rel_map:
        url = url_for('%s.%s' % ('jobs', endpoint), job_id=job['id'])
        job['links'].append({'rel': rel, 'href': url, 'title': title})


@app.route('/', methods=['POST'])
@app.args({'hostname': Arg(str), 'properties': Arg(None)})
@app.need_authentication()
def create(hostname, properties):
    """POST /resources"""
    props = json.loads(properties)
    user = g.current_user
    if (user == 'oar') or (user == 'root'):
        resource_fields = {'network_address': hostname}
        resource_fields.update(props)
        ins = Resource.__table__.insert().values(**resource_fields)
        result = db.session.execute(ins)
        resource_id = result.inserted_primary_key[0]
        g.data['id'] = resource_id
        g.data['uri'] = url_for('%s.%s' % (app.name, 'show'), resource_id=resource_id)
        g.data['status'] = 'ok'
    else:
        g.data['status'] = 'Bad user'

