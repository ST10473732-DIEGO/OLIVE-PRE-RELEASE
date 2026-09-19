"""Legacy import/command compatibility. All objects belong to canonical olive."""
import importlib,importlib.abc,importlib.util,sys

class _AliasLoader(importlib.abc.Loader):
    def __init__(self,name):self.name=name
    def create_module(self,spec):return importlib.import_module(self.name)
    def exec_module(self,module):pass
    def get_code(self,fullname):
        spec=importlib.util.find_spec(self.name)
        return spec.loader.get_code(self.name)

class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if not fullname.startswith('dmdo.'):return None
        name='olive'+fullname[4:]
        spec=importlib.util.find_spec(name)
        if spec is None:return None
        return importlib.util.spec_from_loader(fullname,_AliasLoader(name),is_package=spec.submodule_search_locations is not None)

sys.meta_path.insert(0,_AliasFinder())
sys.modules[__name__]=importlib.import_module('olive')
