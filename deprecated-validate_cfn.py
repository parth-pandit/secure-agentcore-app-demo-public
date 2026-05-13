import yaml

class CfnLoader(yaml.SafeLoader):
    pass

def cfn_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)

CfnLoader.add_multi_constructor('!', cfn_constructor)

with open('infrastructure/cloudformation/templates/agentcore-app-stack.yaml', 'r') as f:
    data = yaml.load(f, Loader=CfnLoader)

resources = data.get('Resources', {})
resource_keys = list(resources.keys())
print('Resources found:', resource_keys)

pe = resources.get('PolicyEngine')
if pe:
    print()
    print('PolicyEngine resource:')
    print('  Type:', pe.get('Type'))
    print('  Properties:', pe.get('Properties'))
    print('  DependsOn:', pe.get('DependsOn', '(none -- correct)'))

    # Verify it appears before AgentCoreGateway
    pe_idx = resource_keys.index('PolicyEngine')
    gw_idx = resource_keys.index('AgentCoreGateway')
    print()
    print('  PolicyEngine index:', pe_idx, ', AgentCoreGateway index:', gw_idx)
    print('  PolicyEngine before AgentCoreGateway:', pe_idx < gw_idx)
else:
    print('ERROR: PolicyEngine not found!')
