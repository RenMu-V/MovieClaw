from movieclaw_jellyfin.catalog import DtoContext, library_view_dto
from movieclaw_db.models import Library

def test_yamby_mixed_view_uses_nullable_collection_not_folders():
    lib=Library(id=10,name='Mixed',kind='mixed',source='tmdb',root_paths=[])
    ctx=DtoContext(server_id='server')
    ctx.client='Yamby'
    dto=library_view_dto(ctx,lib)
    assert dto['Type']=='CollectionFolder' and dto['IsFolder']
    assert 'CollectionType' not in dto
    other=library_view_dto(DtoContext(server_id='server'),lib)
    assert other['CollectionType']=='folders'
