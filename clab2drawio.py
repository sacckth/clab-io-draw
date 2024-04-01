from N2G import drawio_diagram
import yaml
from collections import defaultdict
import argparse
import os

def assign_graphlevels(nodes, links, verbose=False):
    """
    Assigns hierarchical graph levels to nodes based on connections or optional labels
    Returns a sorted list of nodes, their graph levels, and connection details.
    """
    node_graphlevels = {}
    for node, node_info in nodes.items():
        # Check if 'labels' is a dictionary
        labels = node_info.get('labels', {})
        if isinstance(labels, dict):
            graph_level = labels.get('graph-level', -1)
            graphlevel = labels.get('graphlevel', -1)
            node_graphlevels[node] = graph_level if graph_level != -1 else graphlevel
        else:
            node_graphlevels[node] = -1

    # Initialize the connections dictionary
    connections = {node: {'upstream': set(), 'downstream': set()} for node in nodes}
    for link in links:
        source, target = link['source'], link['target']
        connections[source]['downstream'].add(target)
        connections[target]['upstream'].add(source)

    # Helper function to assign graphlevel by recursively checking connections
    def set_graphlevel(node, current_graphlevel, verbose=False):
        if node_graphlevels[node] != -1 and node_graphlevels[node] < current_graphlevel:
            # Skip setting graphlevel if it is manually set and higher than the current graphlevel
            return
        node_graphlevels[node] = max(node_graphlevels[node], current_graphlevel)
        for downstream_node in connections[node]['downstream']:
            set_graphlevel(downstream_node, current_graphlevel + 1)

    # Start by setting the graphlevel of nodes with no upstream connections or with a manually set graphlevel
    for node in nodes:
        if node_graphlevels[node] == -1 and not connections[node]['upstream']:
            set_graphlevel(node, 0)
        elif node_graphlevels[node] != -1:
            # Manually set the graphlevel for nodes with a specified graphlevel
            set_graphlevel(node, node_graphlevels[node])

    # Dynamic approach to infer graphlevels from names
    prefix_map = {}
    for node in [n for n, graphlevel in node_graphlevels.items() if graphlevel == -1]:
        # Extract prefix (alphabetic part of the name)
        prefix = ''.join(filter(str.isalpha, node))
        if prefix not in prefix_map:
            prefix_map[prefix] = []
        prefix_map[prefix].append(node)

    # Attempt to assign graphlevels based on these groupings
    graphlevel_counter = max(node_graphlevels.values()) + 1
    for prefix, nodes in prefix_map.items():
        for node in nodes:
            node_graphlevels[node] = graphlevel_counter
        graphlevel_counter += 1

    sorted_nodes = sorted(node_graphlevels, key=lambda n: (node_graphlevels[n], n))
    return sorted_nodes, node_graphlevels, connections

def center_align_nodes(nodes_by_graphlevel, positions, layout='vertical', verbose=False):
    """
    Center align nodes within each graphlevel based on the layout layout and ensure
    they are nicely distributed to align with the graphlevel above.
    """
    
    if layout == 'vertical':
        prev_graphlevel_center = None
        for graphlevel, nodes in sorted(nodes_by_graphlevel.items()):
            if prev_graphlevel_center is None:
                # For the first graphlevel, calculate its center and use it as the previous center for the next level
                graphlevel_min_x = min(positions[node][0] for node in nodes)
                graphlevel_max_x = max(positions[node][0] for node in nodes)
                prev_graphlevel_center = (graphlevel_min_x + graphlevel_max_x) / 2
            else:
                # Calculate current graphlevel's width and its center
                graphlevel_width = max(positions[node][0] for node in nodes) - min(positions[node][0] for node in nodes)
                graphlevel_center = sum(positions[node][0] for node in nodes) / len(nodes)
                
                # Calculate offset to align current graphlevel's center with the previous graphlevel's center
                offset = prev_graphlevel_center - graphlevel_center
                
                # Apply offset to each node in the current graphlevel
                for node in nodes:
                    positions[node] = (positions[node][0] + offset, positions[node][1])
                
                # Update prev_graphlevel_center for the next level
                prev_graphlevel_center = sum(positions[node][0] for node in nodes) / len(nodes)
    else:  # Horizontal layout
        prev_graphlevel_center = None
        for graphlevel, nodes in sorted(nodes_by_graphlevel.items()):
            if prev_graphlevel_center is None:
                # For the first graphlevel, calculate its center and use it as the previous center for the next level
                graphlevel_min_y = min(positions[node][1] for node in nodes)
                graphlevel_max_y = max(positions[node][1] for node in nodes)
                prev_graphlevel_center = (graphlevel_min_y + graphlevel_max_y) / 2
            else:
                # Calculate current graphlevel's height and its center
                graphlevel_height = max(positions[node][1] for node in nodes) - min(positions[node][1] for node in nodes)
                graphlevel_center = sum(positions[node][1] for node in nodes) / len(nodes)
                
                # Calculate offset to align current graphlevel's center with the previous graphlevel's center
                offset = prev_graphlevel_center - graphlevel_center
                
                # Apply offset to each node in the current graphlevel
                for node in nodes:
                    positions[node] = (positions[node][0], positions[node][1] + offset)
                
                # Update prev_graphlevel_center for the next level
                prev_graphlevel_center = sum(positions[node][1] for node in nodes) / len(nodes)
            

def adjust_intermediary_nodes_same_level(nodes_by_graphlevel, connections, positions, layout, verbose=False):
    """
    Identifies and adjusts positions of intermediary nodes on the same level to improve graph readability.
    Intermediary nodes directly connected to their preceding and following nodes are repositioned based on the layout.
    Returns the list of adjusted intermediary nodes and their new positions.
    """

    intermediaries = []
    if verbose:
        print("\nIdentifying intermediary nodes on the same level:")

    # Adjustment amount
    adjustment_amount = 100  # Adjust this value as needed

    # Iterate through each level and its nodes
    for level, nodes in nodes_by_graphlevel.items():
        # Determine the sorting key based on layout
        sort_key = lambda node: positions[node][1] if layout == 'horizontal' else positions[node][0]

        # Sort nodes based on their position
        sorted_nodes = sorted(nodes, key=sort_key)

        # Check connectivity and position to identify intermediaries
        for i in range(1, len(sorted_nodes) - 1):  # Skip the first and last nodes
            prev_node, current_node, next_node = sorted_nodes[i-1], sorted_nodes[i], sorted_nodes[i+1]

            # Ensure prev_node and next_node are directly connected
            if next_node in connections[prev_node].get('downstream', []) or prev_node in connections[next_node].get('upstream', []):
                # Further check if current_node is directly connected to both prev_node and next_node
                if prev_node in connections[current_node].get('upstream', []) and next_node in connections[current_node].get('downstream', []):
                    intermediaries.append(current_node)
                    if verbose:
                        print(f"{current_node} is an intermediary between {prev_node} and {next_node} on level {level}")

                    # Adjust the position of the intermediary node based on the layout
                    if layout == 'horizontal':
                        # Move left for horizontal layout
                        positions[current_node] = (positions[current_node][0] - adjustment_amount, positions[current_node][1])
                    else:
                        # Move down for vertical layout
                        positions[current_node] = (positions[current_node][0], positions[current_node][1] + adjustment_amount)
                    if verbose:
                        print(f"Position of {current_node} adjusted to {positions[current_node]}")

    return intermediaries, positions


def adjust_intermediary_nodes(nodes_by_graphlevel, connections, positions, layout, verbose=False):
    """
    Adjusts positions of intermediary nodes in a graph to avoid alignment issues between non-adjacent levels. 
    It identifies nodes with indirect connections spanning multiple levels and repositions them to enhance clarity.
    Returns a set of nodes that were adjusted.
    """

    node_to_graphlevel = {node: level for level, nodes in nodes_by_graphlevel.items() for node in nodes}
    adjusted_nodes = set()  # Set to track adjusted nodes
    upstream_positions = {}

    # Get all connections between non-adjacent levels
    non_adjacent_connections = []
    all_intermediary_nodes = set()
    for node, links in connections.items():
        node_level = node_to_graphlevel[node]
        for upstream in links['upstream']:
            upstream_level = node_to_graphlevel[upstream]

            # Check if the level is non-adjacent
            if abs(upstream_level - node_level) >= 2:
                # Check for the level between if it the nodes has adjacent connections to a node in this level
                intermediary_level = upstream_level + 1 if upstream_level < node_level else upstream_level - 1
                has_adjacent_connection = any(node_to_graphlevel[n] == intermediary_level for n in connections[upstream]['downstream']) or \
                                          any(node_to_graphlevel[n] == intermediary_level for n in connections[node]['upstream'])

                if has_adjacent_connection:
                    if verbose:
                        print(f"Adjacent connection to intermediary level: {upstream} -> {node} -> {intermediary_level}")
                    intermediary_nodes_at_level = [n for n in connections[upstream]['downstream'] if node_to_graphlevel[n] == intermediary_level] + \
                                                   [n for n in connections[node]['upstream'] if node_to_graphlevel[n] == intermediary_level]
                    
                    if verbose:
                        print(f"Nodes at intermediary level {intermediary_level}: {', '.join(intermediary_nodes_at_level)}")

                        for intermediary_node in intermediary_nodes_at_level:
                            print(f"{intermediary_node} is between {upstream} and {node}")

                        print(f"Nodes at intermediary level {intermediary_level}: {', '.join(intermediary_nodes_at_level)}")

                    all_intermediary_nodes.update(intermediary_nodes_at_level)

                    for intermediary_node in intermediary_nodes_at_level:
                        # Store the position of the upstream node for each intermediary node
                        upstream_positions[intermediary_node] = (upstream, positions[upstream])

                else:
                    for downstream in links['downstream']:
                        downstream_level = node_to_graphlevel[downstream]
                        if abs(downstream_level - node_level) >= 2:
                            non_adjacent_connections.append((upstream, node, downstream))
                            all_intermediary_nodes.add(node)

    # Group intermediary nodes by their levels
    intermediary_nodes_by_level = {}
    for node in all_intermediary_nodes:
        level = node_to_graphlevel[node]
        if level not in intermediary_nodes_by_level:
            intermediary_nodes_by_level[level] = []
        intermediary_nodes_by_level[level].append(node)

    # Print the intermediary nodes by level
    if verbose:
        print("\nIntermediary nodes by level:", intermediary_nodes_by_level)

    # Select a group of intermediary nodes by level
    if intermediary_nodes_by_level != {}:
        selected_level = max(intermediary_nodes_by_level.keys(), key=lambda lvl: len(intermediary_nodes_by_level[lvl]))
        selected_group = intermediary_nodes_by_level[selected_level]

        # Sort the selected group by their position to find the top and bottom nodes
        # The sorting key changes based on the layout
        if layout == 'horizontal':
            sorted_group = sorted(selected_group, key=lambda node: positions[node][1])
        else:  # 'vertical'
            sorted_group = sorted(selected_group, key=lambda node: positions[node][0])

        top_node = sorted_group[0]
        bottom_node = sorted_group[-1]

        # Check if there's only one intermediary node and multiple levels
        if len(sorted_group) == 1 and len(intermediary_nodes_by_level) > 1:
            node = sorted_group[0]
            # Adjust position based on layout and axis alignment
            if layout == 'horizontal' and positions[node][1] == positions[upstream][1]:
                if verbose:
                    print(f"Node {node} (before): {positions[node]}")
                positions[node] = (positions[node][0], positions[node][1] - 150)
                if verbose:
                    print(f"Node {node} (adjusted): {positions[node]}")
                adjusted_nodes.add(node)
            elif layout == 'vertical' and positions[node][0] == positions[upstream][0]:
                if verbose:
                    print(f"Node {node} (before): {positions[node]}")
                positions[node] = (positions[node][0] - 150, positions[node][1])
                if verbose:
                    print(f"Node {node} (adjusted): {positions[node]}")
                adjusted_nodes.add(node)

        # Check if there are top and bottom nodes to adjust and more than one level
        elif len(sorted_group) > 1:
            # Print positions before adjustment
            if verbose:
                print(f"Top Node (before): {top_node} at position {positions[top_node]}")
                print(f"Bottom Node (before): {bottom_node} at position {positions[bottom_node]}")

            if layout == 'horizontal':
                # Check Y-axis alignment for top_node using upstream position
                if positions[top_node][1] == upstream_positions[top_node][1][1]:  # [1][1] to access the Y position
                    if verbose:
                        print(f"{top_node} is aligned with its upstream {upstream_positions[top_node][0]} on the Y-axis")
                    positions[top_node] = (positions[top_node][0], positions[top_node][1] - 100)
                    adjusted_nodes.add(top_node)
                # Repeat for bottom_node
                if positions[bottom_node][1] == upstream_positions[bottom_node][1][1]:
                    if verbose:
                        print(f"{bottom_node} is aligned with its upstream {upstream_positions[bottom_node][0]} on the Y-axis")
                    positions[bottom_node] = (positions[bottom_node][0], positions[bottom_node][1] + 100)
                    adjusted_nodes.add(bottom_node)
            elif layout == 'vertical':
                # Check X-axis alignment for top_node using upstream position
                if positions[top_node][0] == upstream_positions[top_node][1][0]:  # [1][0] to access the X position
                    if verbose:
                        print(f"{top_node} is aligned with its upstream {upstream_positions[top_node][0]} on the X-axis")
                    positions[top_node] = (positions[top_node][0] - 100, positions[top_node][1])
                    adjusted_nodes.add(top_node)
                # Repeat for bottom_node
                if positions[bottom_node][0] == upstream_positions[bottom_node][1][0]:
                    if verbose:
                        print(f"{bottom_node} is aligned with its upstream {upstream_positions[bottom_node][0]} on the X-axis")
                    positions[bottom_node] = (positions[bottom_node][0] + 100, positions[bottom_node][1])
                    adjusted_nodes.add(bottom_node)

            # Print positions after adjustment
            if verbose:
                print(f"Top Node (adjusted): {top_node} at position {positions[top_node]}")
                print(f"Bottom Node (adjusted): {bottom_node} at position {positions[bottom_node]}")

    return adjusted_nodes
    

def calculate_positions(sorted_nodes, links, node_graphlevels, connections, layout='vertical', verbose=False):
    """
    Calculates and assigns positions to nodes for graph visualization based on their hierarchical levels and connectivity.
    Organizes nodes by graph level, applies prioritization within levels based on connectivity, and adjusts positions to enhance readability.
    Aligns and adjusts intermediary nodes to address alignment issues and improve visual clarity.
    Returns a dictionary mapping each node to its calculated position.
    """

    x_start, y_start = 100, 100
    padding_x, padding_y = 200, 200
    positions = {}
    adjacency = defaultdict(set)

    if verbose:
        print("Sorted nodes before calculate_positions:", sorted_nodes)

    # Build adjacency list
    for link in links:
        src, dst = link['source'], link['target']
        adjacency[src].add(dst)
        adjacency[dst].add(src)

    def prioritize_placement(nodes, adjacency, node_graphlevels, layout, verbose=False):
        # Calculate connection counts within the same level
        connection_counts_within_level = {}
        for node in nodes:
            level = node_graphlevels[node]
            connections_within_level = [n for n in adjacency[node] if n in nodes and node_graphlevels[n] == level]
            connection_counts_within_level[node] = len(connections_within_level)
        
        # Determine if sorting is needed by checking if any node has more than one connection within the level
        needs_sorting = any(count > 1 for count in connection_counts_within_level.values())
        
        if not needs_sorting:
            # If no sorting is needed, return the nodes in their original order
            return nodes
        
        # Separate nodes by their connection count within the level
        multi_connection_nodes = [node for node, count in connection_counts_within_level.items() if count > 1]
        single_connection_nodes = [node for node, count in connection_counts_within_level.items() if count == 1]
        
        # Sort nodes with multiple connections
        multi_connection_nodes_sorted = sorted(multi_connection_nodes, key=lambda node: (-len(adjacency[node]), node))
        
        # Sort single connection nodes
        single_connection_nodes_sorted = sorted(single_connection_nodes, key=lambda node: (len(adjacency[node]), node))
        
        # Merge single and multi-connection nodes, placing single-connection nodes at the ends
        ordered_nodes = single_connection_nodes_sorted[:len(single_connection_nodes_sorted)//2] + \
                        multi_connection_nodes_sorted + \
                        single_connection_nodes_sorted[len(single_connection_nodes_sorted)//2:]
        
        return ordered_nodes

    # Organize nodes by graphlevel and order within each graphlevel
    nodes_by_graphlevel = defaultdict(list)
    for node in sorted_nodes:
        nodes_by_graphlevel[node_graphlevels[node]].append(node)

    for graphlevel, graphlevel_nodes in nodes_by_graphlevel.items():
        ordered_nodes = prioritize_placement(graphlevel_nodes, adjacency, node_graphlevels, layout, verbose=verbose)
    
        for i, node in enumerate(ordered_nodes):
            if layout == 'vertical':
                positions[node] = (x_start + i * padding_x, y_start + graphlevel * padding_y)
            else:
                positions[node] = (x_start + graphlevel * padding_x, y_start + i * padding_y)
    # First, ensure all nodes are represented in node_graphlevels, even if missing from the adjacency calculations
    missing_nodes = set(sorted_nodes) - set(positions.keys())
    for node in missing_nodes:
        if node not in node_graphlevels:
            # Assign a default graphlevel if somehow missing
            node_graphlevels[node] = max(node_graphlevels.values()) + 1  

    # Reorganize nodes by graphlevel after including missing nodes
    nodes_by_graphlevel = defaultdict(list)
    for node in sorted_nodes:
        graphlevel = node_graphlevels[node]
        nodes_by_graphlevel[graphlevel].append(node)

    for graphlevel, graphlevel_nodes in nodes_by_graphlevel.items():
        # Sort nodes within the graphlevel to ensure missing nodes are placed at the end
        graphlevel_nodes_sorted = sorted(graphlevel_nodes, key=lambda node: (node not in positions, node))

        for i, node in enumerate(graphlevel_nodes_sorted):
            if node in positions:
                continue  # Skip nodes that already have positions
            # Assign position to missing nodes at the end of their graphlevel
            if layout == 'vertical':
                positions[node] = (x_start + i * padding_x, y_start + graphlevel * padding_y)
            else:
                positions[node] = (x_start + graphlevel * padding_x, y_start + i * padding_y)

    # Call the center_align_nodes function to align graphlevels relative to the widest/tallest graphlevel
    center_align_nodes(nodes_by_graphlevel, positions, layout=layout)

    adjust_intermediary_nodes(nodes_by_graphlevel, connections, positions, layout, verbose=verbose)
    adjust_intermediary_nodes_same_level(nodes_by_graphlevel, connections, positions, layout, verbose=verbose)

    return positions

def create_links(base_style, positions, source, target, source_graphlevel, target_graphlevel, adjacency, layout='vertical', link_index=0, total_links=1, verbose=False):
    """
    Constructs a link style string for a graph visualization, considering the positions and graph levels of source and target nodes.
    Adjusts the link's entry and exit points based on the layout and whether nodes are on the same or different graph levels.
    Supports multiple links between the same nodes by adjusting the positioning to avoid overlaps.
    Returns a style string with parameters defining the link's appearance and positioning.
    """

    source_x, source_y = positions[source]
    target_x, target_y = positions[target]
    # Determine directionality
    left_to_right = source_x < target_x
    above_to_below = source_y < target_y
    
    # Calculate step for multiple links
    step = 0.5 if total_links == 1 else 0.25 + 0.5 * (link_index / (total_links - 1))
    
    if layout == 'horizontal':
        # Different graph levels
        if source_graphlevel != target_graphlevel:
            entryX, exitX = (0, 1) if left_to_right else (1, 0)
            entryY = exitY = step
        # Same graph level
        else:
            if above_to_below:
                entryY, exitY = (0, 1)
            else:
                entryY, exitY = (1, 0)
            entryX = exitX = step
    
    elif layout == 'vertical':
        # Different graph levels
        if source_graphlevel != target_graphlevel:
            entryY, exitY = (0, 1) if above_to_below else (1, 0)
            entryX = exitX = step
        # Same graph level
        else:
            if left_to_right:
                entryX, exitX = (0, 1)
            else:
                entryX, exitX = (1, 0)
            entryY = exitY = step
            
    links  = f"{base_style}entryY={entryY};exitY={exitY};entryX={entryX};exitX={exitX};"
    return links


def add_nodes_and_links(diagram, nodes, positions, links, node_graphlevels, no_links=False, layout='vertical', verbose=False, base_style=None, link_style=None, custom_styles=None, icon_to_group_mapping=None, src_label_style=None, trgt_label_style=None):
    """
    Adds nodes and links to a diagram based on their positions, connectivity, and additional properties.
    Utilizes custom styles for nodes based on their roles (e.g., routers, switches, servers) and dynamically adjusts link styles to represent connectivity accurately.
    Supports conditional inclusion of links and customization of the diagram's layout (vertical or horizontal).
    Parameters include the diagram object, node and link data, positioning information, and flags for link inclusion and verbosity.
    """

    for node_name, node_info in nodes.items():
        # Check for 'graph-icon' label and map it to the corresponding group
        labels = node_info.get('labels') or {}
        icon_label = labels.get('graph-icon', 'default')
        if icon_label in icon_to_group_mapping:
            group = icon_to_group_mapping[icon_label]
        else:
            # Determine the group based on the node's name if 'graph-icon' is not specified
            if "client" in node_name:
                group = "server"
            elif "leaf" in node_name:
                group = "leaf"
            elif "spine" in node_name:
                group = "spine"
            elif "dcgw" in node_name:
                group = "dcgw"
            else:
                group = "default"  # Fallback to 'default' if none of the conditions are met

        style = custom_styles.get(group, base_style)
        x_pos, y_pos = positions[node_name]
        # Add each node to the diagram with the given x and y position.
        diagram.add_node(id=node_name, label=node_name, x_pos=x_pos, y_pos=y_pos, style=style, width=75, height=75)

    # Initialize a counter for links between the same nodes
    link_counter = defaultdict(lambda: 0)

    total_links_between_nodes = defaultdict(int)
    for link in links:
        source, target = link['source'], link['target']
        link_key = tuple(sorted([source, target]))
        total_links_between_nodes[link_key] += 1

    for link in links:
        source, target = link['source'], link['target']
        source_intf, target_intf = link['source_intf'], link['target_intf']
        source_graphlevel = node_graphlevels.get(source.split(':')[0], -1)
        target_graphlevel = node_graphlevels.get(target.split(':')[0], -1)
        link_key = tuple(sorted([source, target]))
        link_index = link_counter[link_key]

        # Increment link counter for next time
        link_counter[link_key] += 1
        total_links = total_links_between_nodes[link_key]

        source_graphlevel = node_graphlevels[source]
        target_graphlevel = node_graphlevels[target]

        adjacency = defaultdict(set)

        # Build adjacency list
        for link in links:
            src, dst = link['source'], link['target']
            adjacency[src].add(dst)
            adjacency[dst].add(src)

        unique_link_style = create_links(base_style=link_style, positions=positions, source=source, target=target, source_graphlevel=source_graphlevel, target_graphlevel=target_graphlevel, link_index=link_index, total_links=total_links, adjacency=adjacency, layout=layout)

        # Add the link to the diagram with the determined unique style
        if not no_links:
            diagram.add_link(
                source=source, target=target,
                src_label=source_intf, trgt_label=target_intf,
                src_label_style=src_label_style, trgt_label_style=trgt_label_style,
                style=unique_link_style
                link_id=f"{source}:{source_intf}:{target}:{target_intf}"
            )

def load_styles_from_config(config_path):
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

    base_style = config['base_style']
    link_style = config['link_style']
    src_label_style = config['src_label_style']
    trgt_label_style = config['trgt_label_style']
    
    # Prepend base_style to each custom style
    custom_styles = {key: base_style + value for key, value in config['custom_styles'].items()}
    
    icon_to_group_mapping = config['icon_to_group_mapping']

    return base_style, link_style, src_label_style, trgt_label_style, custom_styles, icon_to_group_mapping


def main(input_file, output_file, theme, include_unlinked_nodes=False, no_links=False, layout='vertical', verbose=False):
>>>>>>> upstream/main
    """
    Generates a diagram from a given topology definition file, organizing and displaying nodes and links.
    
    Processes an input YAML file containing node and link definitions, extracts relevant information,
    and applies logic to determine node positions and connectivity. The function supports filtering out unlinked nodes,
    optionally excluding links, choosing the layout orientation, and toggling verbose output for detailed processing logs.
    
    Outputs the generated diagram to a specified file, creating directories as needed.

    Parameters:
    - input_file (str): Path to the input YAML file with topology definitions.
    - output_file (str): Path where the output diagram file will be saved.
    - include_unlinked_nodes (bool): Flag to include nodes that do not have any links.
    - no_links (bool): Flag to exclude links from the diagram.
    - layout (str): Layout orientation ('vertical' or 'horizontal') for the diagram.
    - verbose (bool, optional): If True, enables detailed logging of the function's operations.
    """

    with open(input_file, 'r') as file:
        containerlab_data = yaml.safe_load(file)

   # Nodes remain the same
    nodes = containerlab_data['topology']['nodes']

    # Prepare the links list by extracting source and target from each link's 'endpoints'
    links = []
    for link in containerlab_data['topology'].get('links', []):
        endpoints = link.get('endpoints')
        if endpoints:
            source_node, source_intf = endpoints[0].split(":")
            target_node, target_intf = endpoints[1].split(":")
            # Add link only if both source and target nodes exist
            if source_node in nodes and target_node in nodes:
                links.append({'source': source_node, 'target': target_node, 'source_intf': source_intf, 'target_intf': target_intf})

    if not include_unlinked_nodes:
        linked_nodes = set()
        for link in links:
            linked_nodes.add(link['source'])
            linked_nodes.add(link['target'])
        nodes = {node: info for node, info in nodes.items() if node in linked_nodes}

    sorted_nodes, node_graphlevels, connections = assign_graphlevels(nodes, links, verbose=verbose)
    positions = calculate_positions(sorted_nodes, links, node_graphlevels, connections, layout=layout, verbose=verbose)

    # Create a draw.io diagram instance
    diagram = drawio_diagram()

    # Add a diagram page
    diagram.add_diagram("Network Topology")

    if theme in ['bright', 'dark']:
        config_path = os.path.join(script_dir, f'styles/{theme}.yaml')
    else:
        # Assume the user has provided a custom path
        config_path = theme


    # Add nodes and links to the diagram
    base_style, link_style, src_label_style, trgt_label_style, custom_styles, icon_to_group_mapping = load_styles_from_config(config_path)
    add_nodes_and_links(diagram, nodes, positions, links, node_graphlevels, no_links=no_links, layout=layout, verbose=verbose, base_style=base_style, link_style=link_style, custom_styles=custom_styles, icon_to_group_mapping=icon_to_group_mapping, src_label_style=src_label_style, trgt_label_style=trgt_label_style)

    # If output_file is not provided, generate it from input_file
    if not output_file:
        output_file = os.path.splitext(input_file)[0] + ".drawio"
        
    output_folder = os.path.dirname(output_file) or "."
    output_filename = os.path.basename(output_file)
    os.makedirs(output_folder, exist_ok=True)

    diagram.dump_file(filename=output_filename, folder=output_folder)

    print("Saved file to:", output_file)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate a topology diagram from a containerlab YAML or draw.io XML file.')
    parser.add_argument('-i', '--input', required=True, help='The filename of the input file (containerlab YAML for diagram generation).')
    parser.add_argument('-o', '--output', required=False, help='The output file path for the generated diagram (draw.io format).')
    parser.add_argument('--include-unlinked-nodes', action='store_true', help='Include nodes without any links in the topology diagram')
    parser.add_argument('--no-links', action='store_true', help='Do not draw links between nodes in the topology diagram')
    parser.add_argument('--layout', type=str, default='vertical', choices=['vertical', 'horizontal'], help='Specify the layout of the topology diagram (vertical or horizontal)')
    parser.add_argument('--theme', default='bright', help='Specify the theme for the diagram (bright, dark) or the path to a custom style config file.')  
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output for debugging purposes')  
    return parser.parse_args()
    
if __name__ == "__main__":
    args = parse_arguments()

    script_dir = os.path.dirname(__file__)

    main(args.input, args.output, args.theme, args.include_unlinked_nodes, args.no_links, args.layout, args.verbose)


