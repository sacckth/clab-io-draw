from N2G import drawio_diagram
from collections import defaultdict
import yaml, argparse, os, re, json
import xml.etree.ElementTree as ET

class CustomDrawioDiagram(drawio_diagram):
    # Overriding the drawio_diagram_xml with shadow=0
    drawio_diagram_xml = """
    <diagram id="{id}" name="{name}">
      <mxGraphModel dx="{width}" dy="{height}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0" background="#000000">
        <root>
          <mxCell id="0"/>   
          <mxCell id="1" parent="0"/>
        </root>
      </mxGraphModel>
    </diagram>
    """
    
    def __init__(self, styles, node_duplicates="skip", link_duplicates="skip"):


        background = styles['background']
        shadow = styles['shadow']
        grid = styles['grid']
        pagew = styles['pagew']
        pageh = styles['pageh']

        self.drawio_diagram_xml = f"""
        <diagram id="{{id}}" name="{{name}}">
          <mxGraphModel dx="{{width}}" dy="{{height}}" grid="{grid}" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{pagew}" pageHeight="{pageh}" math="0" shadow="{shadow}" background="{background}">
            <root>
              <mxCell id="0"/>   
              <mxCell id="1" parent="0"/>
            </root>
          </mxGraphModel>
        </diagram>
        """

        super().__init__(node_duplicates, link_duplicates, )

    def calculate_new_group_positions(self, obj_pos_old, group_pos):
        # Adjust object positions relative to the new group's position
        obj_pos_new = (obj_pos_old[0] - group_pos[0], obj_pos_old[1] - group_pos[1])
        return obj_pos_new

    def group_nodes(self, member_objects, group_id, style=""):
        # Initialize bounding box coordinates
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')

        object_positions = []  # To store all object positions

        # Process each member object to update the bounding box
        for obj_id in member_objects:
            obj_mxcell = self.current_root.find(f".//object[@id='{obj_id}']/mxCell")
            if obj_mxcell is not None:
                geometry = obj_mxcell.find("./mxGeometry")
                if geometry is not None:
                    x, y = float(geometry.get('x', '0')), float(geometry.get('y', '0'))
                    width, height = float(geometry.get('width', '0')), float(geometry.get('height', '0'))

                    # Store object positions and update bounding box
                    object_positions.append((obj_id, x, y, width, height))
                    min_x, min_y = min(min_x, x), min(min_y, y)
                    max_x, max_y = max(max_x, x + width), max(max_y, y + height)

        # Define the group's position and size based on the bounding box
        group_x, group_y = min_x, min_y
        group_width, group_height = max_x - min_x, max_y - min_y

        # Create the group cell in the XML structure
        group_cell_xml = f"""
        <mxCell id="{group_id}" value="" style="{style}" vertex="1" connectable="0" parent="1">
        <mxGeometry x="{group_x}" y="{group_y}" width="{group_width}" height="{group_height}" as="geometry" />
        </mxCell>
        """
        group_cell = ET.fromstring(group_cell_xml)
        self.current_root.append(group_cell)

        # Update positions of all objects within the group
        for obj_id, x, y, _, _ in object_positions:
            obj_pos_old = (x, y)
            obj_pos_new = self.calculate_new_group_positions(obj_pos_old, (group_x, group_y))

            obj_mxcell = self.current_root.find(f".//object[@id='{obj_id}']/mxCell")
            if obj_mxcell is not None:
                geometry = obj_mxcell.find("./mxGeometry")
                if geometry is not None:
                    geometry.set('x', str(obj_pos_new[0]))
                    geometry.set('y', str(obj_pos_new[1]))
                    obj_mxcell.set("parent", group_id)  # Set the object's parent to the new group

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

def check_node_alignment(source_node_position, target_node_position):
    # Horizontal alignment if y-coordinates are equal
    if source_node_position[1] == target_node_position[1]:
        return 'horizontal'
    # Vertical alignment if x-coordinates are equal
    elif source_node_position[0] == target_node_position[0]:
        return 'vertical'
    return 'none'

def sort_connector_positions(link_connector_positions):

    for link_id, link_info in link_connector_positions.items():
        source_node_position = link_info['source_node_position']
        target_node_position = link_info['target_node_position']
        
        # Check if nodes for this link are aligned (horizontal or vertical)
        node_alignment = check_node_alignment(source_node_position, target_node_position)

        # Proceed to check connector alignment only if nodes are aligned
        if node_alignment != 'none':
            source_connector_pos = link_info['source_connector_position']
            target_connector_pos = link_info['target_connector_position']
            # Check connector alignment based on node alignment direction
            if node_alignment == 'horizontal' and source_connector_pos[1] == target_connector_pos[1]:
                #print(f"Connectors for link {link_id} are nicely aligned horizontally.")
                pass
            elif node_alignment == 'vertical' and source_connector_pos[0] == target_connector_pos[0]:
                pass
                #print(f"Connectors for link {link_id} are nicely aligned vertically.")
            else:
                print(f"Connectors for link {link_id} are not nicely aligned {node_alignment}.")
                #TODO: Adjust them

def add_connector_nodes(diagram, nodes, links, positions, styles, verbose=False):
    # Set connector and node dimensions
    connector_width, connector_height = 8, 8
    node_width, node_height = 75, 75

    # Initialize dictionaries for connector directions and positions
    connector_directions = {node: {'up': 0, 'right': 0, 'down': 0, 'left': 0} for node in nodes}
    connector_positions = {node: {'up': [], 'right': [], 'down': [], 'left': []} for node in nodes}
    link_connector_positions = {}

    if verbose:
        print(f"Total number of links: {len(links)}")
        print(f"Expected number of connectors: {len(links) * 2}")

    # Go through each link to determine the direction for both the source and target nodes
    for link in links:
        source = link['source']
        target = link['target']

        # Parse the unique link style parameters
        style_params = dict(param.split('=') for param in link['unique_link_style'].split(';') if '=' in param)
        exitY = float(style_params.get('exitY', '0.5'))
        exitX = float(style_params.get('exitX', '0.5'))
        entryY = float(style_params.get('entryY', '0.5'))
        entryX = float(style_params.get('entryX', '0.5'))

        # Determine the direction based on exit positions for the source node
        if exitY == 0:
            connector_directions[source]['up'] += 1
        elif exitY == 1:
            connector_directions[source]['down'] += 1

        if exitX == 0:
            connector_directions[source]['left'] += 1
        elif exitX == 1:
            connector_directions[source]['right'] += 1

        # Determine the direction based on entry positions for the target node
        if entryY == 0:
            connector_directions[target]['up'] += 1
        elif entryY == 1:
            connector_directions[target]['down'] += 1

        if entryX == 0:
            connector_directions[target]['left'] += 1
        elif entryX == 1:
            connector_directions[target]['right'] += 1

    # Calculate the connector positions based on the directions
    for node, directions in connector_directions.items():
        for direction, total_connectors in directions.items():
            for count in range(total_connectors):
                spacing = (node_width if direction in ['up', 'down'] else node_height) / (total_connectors + 1)
                position = spacing * (count + 1)

                if direction == 'up':
                    connector_pos = (position - connector_width / 2, -connector_height / 2)
                elif direction == 'down':
                    connector_pos = (position - connector_width / 2, node_height - connector_height / 2)
                elif direction == 'left':
                    connector_pos = (-connector_width / 2, position - connector_height / 2)
                elif direction == 'right':
                    connector_pos = (node_width - connector_width / 2, position - connector_height / 2)

                # Translate local connector position to global coordinates
                global_connector_pos = (
                    positions[node][0] + connector_pos[0],
                    positions[node][1] + connector_pos[1]
                )
                connector_positions[node][direction].append(global_connector_pos)

    # First loop: Populate link_connector_positions
    for link in links:
        source = link['source']
        target = link['target']
        source_intf = link['source_intf']
        target_intf = link['target_intf']

        # Parse the unique link style parameters
        style_params = dict(param.split('=') for param in link['unique_link_style'].split(';') if '=' in param)
        exitY = float(style_params.get('exitY', '0.5'))
        exitX = float(style_params.get('exitX', '0.5'))
        entryY = float(style_params.get('entryY', '0.5'))
        entryX = float(style_params.get('entryX', '0.5'))

        # Determine the direction based on exit positions for the source node
        source_direction = None
        if exitY == 0:
            source_direction = 'up'
        elif exitY == 1:
            source_direction = 'down'
        elif exitX == 0:
            source_direction = 'left'
        elif exitX == 1:
            source_direction = 'right'

        # Determine the direction based on entry positions for the target node
        target_direction = None
        if entryY == 0:
            target_direction = 'up'
        elif entryY == 1:
            target_direction = 'down'
        elif entryX == 0:
            target_direction = 'left'
        elif entryX == 1:
            target_direction = 'right'

        # Get the connector positions for the source and target nodes
        source_connector_pos = connector_positions[source][source_direction].pop(0) if connector_positions[source][source_direction] else None
        target_connector_pos = connector_positions[target][target_direction].pop(0) if connector_positions[target][target_direction] else None

        if source_connector_pos and target_connector_pos:
            link_id = f"{source}:{link['source_intf']}:{target}:{link['target_intf']}"
            link_connector_positions[link_id] = {
                'source': source,
                'target': target,
                'target_intf': link['target_intf'],
                'source_intf': link['source_intf'],
                'source_node_position': positions[source],
                'target_node_position': positions[target],
                'source_connector_position': source_connector_pos,
                'target_connector_position': target_connector_pos
            }

    # Sort connector positions
    _sorted_connector_positions = sort_connector_positions(link_connector_positions)

    # Second loop: Add connector nodes to the diagram and create connector links
    connector_links = []
    node_groups = {}  # Dictionary to store groups by node

    for link_id, link_info in link_connector_positions.items():
        source = link_info['source']
        target = link_info['target']
        source_intf = link_info['source_intf']
        target_intf = link_info['target_intf']
        source_connector_pos = link_info['source_connector_position']
        target_connector_pos = link_info['target_connector_position']
        source_cID = f"{source}:{source_intf}:{target}:{target_intf}"
        target_cID = f"{target}:{target_intf}:{source}:{source_intf}"

        # Extract the numeric part from the interface names for the labels
        source_label = re.findall(r'\d+', source_intf)[-1]
        target_label = re.findall(r'\d+', target_intf)[-1]

        if source_connector_pos:            
            if verbose:
                print(f"Adding connector for {source} with ID {source_cID} at position {source_connector_pos} with label {source_label}")
            diagram.add_node(
                id=source_cID,
                label=source_label,
                x_pos=source_connector_pos[0],
                y_pos=source_connector_pos[1],
                width=connector_width,
                height=connector_height,
                style=styles['port_style']
            )

        if target_connector_pos:            
            if verbose:
                print(f"Adding connector for {target} with ID {target_cID} at position {target_connector_pos} with label {target_label}")
            diagram.add_node(
                id=target_cID,
                label=target_label,
                x_pos=target_connector_pos[0],
                y_pos=target_connector_pos[1],
                width=connector_width,
                height=connector_height,
                style=styles['port_style']
            )

        if source not in node_groups:
            node_groups[source] = []
        node_groups[source].append(source_cID)

        if target not in node_groups:
            node_groups[target] = []
        node_groups[target].append(target_cID)

        # Assuming each link has one source and one target connector, pair them to form a connector link
        if source_connector_pos and target_connector_pos:    

            # Calculate center positions
            source_center = (source_connector_pos[0] + connector_width / 2, source_connector_pos[1] + connector_height / 2)
            target_center = (target_connector_pos[0] + connector_width / 2, target_connector_pos[1] + connector_height / 2)

            # Calculate the real middle between the centers for the midpoint connector
            midpoint_center_x = (source_center[0] + target_center[0]) / 2
            midpoint_center_y = (source_center[1] + target_center[1]) / 2

            midpoint_top_left_x = midpoint_center_x - 2
            midpoint_top_left_y = midpoint_center_y - 2

            # Calculate the real middle between the centers
            midpoint_x = (source_center[0] + target_center[0]) / 2
            midpoint_y = (source_center[1] + target_center[1]) / 2

            midpoint_id = f"mid:{source}:{source_intf}:{target}:{target_intf}"  # Adjusted ID format
            if verbose:
                print(f"Creating midpoint connector {midpoint_id} between source {source} and target {target} at position ({midpoint_x}, {midpoint_y})")

            # Add the midpoint connector node
            diagram.add_node(
                id=midpoint_id,
                label='\u200B',
                x_pos=midpoint_top_left_x,
                y_pos=midpoint_top_left_y,
                width=4,
                height=4,
                style=styles['connector_style']
            )

            # Adjust connector_links to include the midpoint connector
            connector_links.append({'source': source_cID, 'target': midpoint_id, 'link_id' : f"{source_cID}-src"})
            connector_links.append({'source': target_cID, 'target': midpoint_id, 'link_id' : f"{target_cID}-trgt"})  

    # Now, create groups for each node's connectors
    for node, connector_ids in node_groups.items():
        group_id = f"group-{node}"
        
        # write node node and group id into one array
        connector_ids.append(node)  

        # Create a group for the connectors
        diagram.group_nodes(member_objects=connector_ids, group_id=group_id, style='group')


    if verbose:
        # Calculate the total number of connectors, including midpoints
        total_connector_count = len(connector_links)  # Each link now includes a midpoint, hence total is directly from connector_links
        print(f"Total number of connectors created: {total_connector_count}")
        
        # Expected connectors is now triple the number of links, since each link generates three connectors (source to midpoint, midpoint to target)
        expected_connector_count = len(links) * 3
        
        if total_connector_count != expected_connector_count:
            print("Warning: The number of connectors created does not match the expected count.")
        else:
            print("All connectors created successfully.")

    return connector_links


def add_links_with_connectors(diagram, connector_links, link_style=None, verbose=False):
    for link in connector_links:
        diagram.add_link(source=link['source'], target=link['target'], style=link_style, label='rate', link_id=link['link_id'])

def add_nodes(diagram, nodes, positions, node_graphlevels, styles):

    base_style = styles['base_style']
    custom_styles = styles['custom_styles']
    icon_to_group_mapping = styles['icon_to_group_mapping']

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

def add_links(diagram, links, positions, node_graphlevels, styles, no_links=False, layout='vertical', verbose=False):
       
    
    # Initialize a counter for links between the same nodes
    link_counter = defaultdict(lambda: 0)
    total_links_between_nodes = defaultdict(int)
    adjacency = defaultdict(set)

    # Construct adjacency list once
    for link in links:
        src, dst = link['source'], link['target']
        adjacency[src].add(dst)
        adjacency[dst].add(src)

    # Prepare link counter and total links
    for link in links:
        source, target = link['source'], link['target']
        link_key = tuple(sorted([source, target]))
        total_links_between_nodes[link_key] += 1

    for link in links:
        source, target = link['source'], link['target']
        source_intf, target_intf = link['source_intf'], link['target_intf']
        source_graphlevel = node_graphlevels.get(source, -1)
        target_graphlevel = node_graphlevels.get(target, -1)
        link_key = tuple(sorted([source, target]))
        link_index = link_counter[link_key]

        link_counter[link_key] += 1
        total_links = total_links_between_nodes[link_key]

        unique_link_style = create_links(base_style=styles['link_style'], positions=positions, source=source, target=target, source_graphlevel=source_graphlevel, target_graphlevel=target_graphlevel, adjacency=adjacency, link_index=link_index, total_links=total_links, layout=layout)
        link['unique_link_style'] = unique_link_style
        link_id=f"{source}:{source_intf}:{target}:{target_intf}"
        link['link_id'] = f"link_id:{link_id}"

        if not no_links:
            diagram.add_link(source=source, target=target, src_label=source_intf, trgt_label=target_intf, src_label_style=styles['src_label_style'], trgt_label_style=styles['trgt_label_style'], style=unique_link_style, link_id=link_id)

def load_styles_from_config(config_path):
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        error_message = f"Error: The specified config file '{config_path}' does not exist."
        print(error_message)
        exit()
    except Exception as e:
        error_message = f"An error occurred while loading the config: {e}"
        print(error_message)
        exit()

    # Initialize the styles dictionary with defaults and override with config values
    styles = {
        'base_style': config['base_style'],
        'link_style': config['link_style'],
        'src_label_style': config['src_label_style'],
        'trgt_label_style': config['trgt_label_style'],
        'port_style': config.get('port_style', ''), 
        'connector_style': config.get('connector_style', ''), 
        'background': config.get('background', "#FFFFFF"),
        'shadow': config.get('shadow', "1"),
        'pagew': config.get('pagew', "827"),
        'pageh': config.get('pageh', "1169"),
        'grid': config.get('grid', "1"),
        # Prepend base_style to each custom style
        'custom_styles': {key: config['base_style'] + value for key, value in config['custom_styles'].items()},
        'icon_to_group_mapping': config['icon_to_group_mapping'],
    }

    return styles


def create_grafana_dashboard(diagram=None,dashboard_filename=None,link_list=[]):
    """
    Creates a Grafana JSON Dashboard using the FlowChart Plugin
    Requires as an input the Drawio Object to embed the XML 
    The Link List obtained by add_nodes_and_links function and 
    the file name
    Metrics format defaults:
      Ingress:   node:itf:in
      Egress:    node:itf:out
      OperState: oper_state:node:itf
    Where `node` comes from the clab node and `itf` from the interface name
    """
    
    # We just need the subtree objects from mxGraphModel.Single page drawings only
    xmlTree = ET.fromstring(diagram.dump_xml())
    subXmlTree=xmlTree.findall('.//mxGraphModel')[0]
    
    # Define Query rules for the Panel, rule_expr needs to match the collector metric name
    # Legend format needs to match the format expected by the metric
    panelQueryList = {
        "IngressTraffic" : {
                    "rule_expr" : "interface_traffic_rate_in_bps",
                    "legend_format" : '{{source}}:{{interface_name}}:in',
                   },
        "EgressTraffic" : {
                    "rule_expr" : "interface_traffic_rate_out_bps",
                    "legend_format" : '{{source}}:{{interface_name}}:out',
                   },
        "ItfOperState" : {
                   "rule_expr" : "interface_oper_state",
                   "legend_format" : 'oper_state:{{source}}:{{interface_name}}',
                   },          
    }
    # Create a targets list to embed in the JSON object, we add all the other default JSON attributes to the list
    targetsList = []
    for query in panelQueryList:
        targetsList.append(gf_dashboard_datasource_target(rule_expr=panelQueryList[query]["rule_expr"],legend_format=panelQueryList[query]["legend_format"], refId=query))
    
    # Create the Rules Data
    rulesData = []
    i=0
    for link in link_list:
        rule = link.split(":")
        if "-src" in link:
            #src port ingress
            rulesData.append(gf_flowchart_rule_traffic(ruleName=f"{rule[1]}:{rule[2]}:in", metric=f"{rule[1]}:{rule[2]}:in",link_id=link,order=i))
            #src port:
            rulesData.append(gf_flowchart_rule_operstate(ruleName=f"oper_state:{rule[1]}:{rule[2]}",metric=f"oper_state:{rule[1]}:{rule[2]}",link_id=link,order=i+2))
            i=i+2
        elif "-trgt" in link: 
            #src port egress, we can also change this for the ingress of remote port but there would not be an end
            rulesData.append(gf_flowchart_rule_traffic(ruleName=f"{rule[1]}:{rule[2]}:out",metric=f"{rule[1]}:{rule[2]}:out",link_id=link,order=i+1))
            #dest port:
            rulesData.append(gf_flowchart_rule_operstate(ruleName=f"oper_state:{rule[3]}:{rule[4]}",metric=f"oper_state:{rule[3]}:{rule[4]}",link_id=link,order=i+3))
            i=i+2
    # Create the Panel
    flowchart_panel=gf_flowchart_panel_template(xml=ET.tostring(subXmlTree, encoding="unicode"),
                                                rulesData=rulesData,
                                                panelTitle="Network Telemetry",
                                                targetsList=targetsList)
    #Create a dashboard from the panel
    dashboard_json=json.dumps(gf_dashboard_template(panels=flowchart_panel,dashboard_name=os.path.splitext(dashboard_filename)[0]),indent=4)
    with open(dashboard_filename,'w') as f:
        f.write(dashboard_json)
        print("Saved Grafana dashboard file to:", dashboard_filename)

def gf_flowchart_rule_traffic(ruleName="traffic:inOrOut",metric=None,link_id=None,order=1):
    """
    Dictionary containg information relevant to the traffic Rules
    """
    rule = {
        "aggregation": "current",
            "alias": ruleName,
            "column": "Time",
            "dateColumn": "Time",
            "dateFormat": "YYYY-MM-DD HH:mm:ss",
            "dateTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "ge",
                "level": 0,
                "value": "0d"
              },
              {
                "color": "rgba(237, 129, 40, 0.89)",
                "comparator": "ge",
                "level": 0,
                "value": "-1d"
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "ge",
                "level": 0,
                "value": "-1w"
              }
            ],
            "decimals": 1,
            "gradient": False,
            "hidden": False,
            "invert": False,
            "mappingType": 1,
            "mapsDat": {
              "events": {
                "dataList": [],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "links": {
                "dataList": [],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "shapes": {
                "dataList": [
                  {
                    "colorOn": "a",
                    "hidden": False,
                    "pattern": link_id,
                    "style": "strokeColor"
                  }
                ],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "texts": {
                "dataList": [
                  {
                    "hidden": False,
                    "pattern": link_id,
                    "textOn": "wmd",
                    "textPattern": "/.*/",
                    "textReplace": "content"
                  }
                ],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              }
            },
            "metricType": "serie",
            "newRule": False,
            "numberTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "ge",
                "level": 0
              },
              {
                "color": "rgba(237, 129, 40, 0.89)",
                "comparator": "ge",
                "level": 0,
                "value": 50
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "ge",
                "level": 0,
                "value": 80
              }
            ],
            "order": order,
            "overlayIcon": False,
            "pattern": metric,
            "rangeData": [],
            "reduce": True,
            "refId": "A",
            "sanitize": False,
            "stringTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*/"
              },
              {
                "color": "rgba(237, 129, 40, 0.89)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*warning.*/"
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*(success|ok).*/"
              }
            ],
            "tooltip": True,
            "tooltipColors": False,
            "tooltipLabel": "",
            "tooltipOn": "a",
            "tpDirection": "v",
            "tpGraph": True,
            "tpGraphScale": "linear",
            "tpGraphSize": "100%",
            "tpGraphType": "line",
            "tpMetadata": False,
            "type": "number",
            "unit": "bps",
            "valueData": []
    }
    return rule

def gf_flowchart_rule_operstate(ruleName="oper_state",metric=None,link_id=None,order=1):
    """
    Dictionary containg information relevant to the Operational State Rules
    """
    rule = {
            "aggregation": "current",
            "alias": ruleName,
            "column": "Time",
            "dateColumn": "Time",
            "dateFormat": "YYYY-MM-DD HH:mm:ss",
            "dateTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "ge",
                "level": 0,
                "value": "0d"
              },
              {
                "color": "rgba(237, 129, 40, 0.89)",
                "comparator": "ge",
                "level": 0,
                "value": "-1d"
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "ge",
                "level": 0,
                "value": "-1w"
              }
            ],
            "decimals": 0,
            "gradient": False,
            "hidden": False,
            "invert": False,
            "mappingType": 1,
            "mapsDat": {
              "events": {
                "dataList": [],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "links": {
                "dataList": [],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "shapes": {
                "dataList": [
                  {
                    "colorOn": "a",
                    "hidden": False,
                    "pattern": link_id,
                    "style": "labelBackgroundColor"
                  }
                ],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              },
              "texts": {
                "dataList": [],
                "options": {
                  "enableRegEx": True,
                  "identByProp": "id",
                  "metadata": ""
                }
              }
            },
            "metricType": "serie",
            "newRule": False,
            "numberTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "ge",
                "level": 0
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "ge",
                "level": 0,
                "value": 1
              }
            ],
            "order": order,
            "overlayIcon": False,
            "pattern": metric,
            "rangeData": [],
            "reduce": True,
            "refId": "A",
            "sanitize": False,
            "stringTHData": [
              {
                "color": "rgba(245, 54, 54, 0.9)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*/"
              },
              {
                "color": "rgba(237, 129, 40, 0.89)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*warning.*/"
              },
              {
                "color": "rgba(50, 172, 45, 0.97)",
                "comparator": "eq",
                "level": 0,
                "value": "/.*(success|ok).*/"
              }
            ],
            "tooltip": False,
            "tooltipColors": False,
            "tooltipLabel": "",
            "tooltipOn": "a",
            "tpDirection": "v",
            "tpGraph": False,
            "tpGraphScale": "linear",
            "tpGraphSize": "100%",
            "tpGraphType": "line",
            "tpMetadata": False,
            "type": "number",
            "unit": "short",
            "valueData": []
          }
    return rule

def gf_flowchart_panel_template(xml=None,rulesData=None,targetsList=None,panelTitle="Network Topology"):
    """
    Dictionary containg information relevant to the Panels Section in the JSON Dashboard
    Embeding of the XML diagram, the Rules and the Targets
    """
    panels = [
         {
           "datasource": {
             "type": "prometheus",
             "uid": "${DS_PROMETHEUS}"
           },
           "flowchartsData": {
             "allowDrawio": True,
             "editorTheme": "kennedy",
             "editorUrl": "https://embed.diagrams.net/",
             "flowcharts": [
               {
                 "center": True,
                 "csv": "",
                 "download": False,
                 "enableAnim": True,
                 "grid": False,
                 "lock": True,
                 "name": "Main",
                 "scale": True,
                 "tooltip": True,
                 "type": "xml",
                 "url": "http://<YourUrl>/<Your XML/drawio file/api>",
                 "xml": xml,
                 "zoom": "100%"
               }
             ]
           },
           "format": "short",
           "graphId": "flowchart_1",
           "gridPos": {
             "h": 20,
             "w": 17,
             "x": 0,
             "y": 0
           },
           "id": 1,
           "rulesData": {
                 "rulesData": rulesData,
           },
           "targets": targetsList,
           "title": panelTitle,
           "type": "agenty-flowcharting-panel",
           "valueName": "current",
           "version": "1.0.0e"
         }
       ]
    return panels

def gf_dashboard_datasource_target(rule_expr="promql_query",legend_format=None, refId="Query1"):
    """
    Dictionary containg information relevant to the Targets queried
    """
    target = {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "expr": rule_expr,
          "instant": False,
          "legendFormat": legend_format,
          "range": True,
          "refId": refId,
    }
    return target

def gf_dashboard_template(panels=None,dashboard_name="lab-telemetry"):
    """
    Dictionary containg information relevant to the Grafana Dashboard Root JSON object
    """
    dashboard = {
       "__inputs": [
         {
           "name": "DS_PROMETHEUS",
           "label": "Prometheus",
           "description": "Autogenerated by clab2grafana.py",
           "type": "datasource",
           "pluginId": "prometheus",
           "pluginName": "Prometheus"
         }
       ],
       "__elements": {},
       "__requires": [
         {
           "type": "panel",
           "id": "agenty-flowcharting-panel",
           "name": "FlowCharting",
           "version": "1.0.0e"
         },
         {
           "type": "grafana",
           "id": "grafana",
           "name": "Grafana",
           "version": "10.3.3"
         },
         {
           "type": "datasource",
           "id": "prometheus",
           "name": "Prometheus",
           "version": "1.0.0"
         }
       ],
       "annotations": {
         "list": [
           {
             "builtIn": 1,
             "datasource": {
               "type": "grafana",
               "uid": "-- Grafana --"
             },
             "enable": True,
             "hide": True,
             "iconColor": "rgba(0, 211, 255, 1)",
             "name": "Annotations & Alerts",
             "type": "dashboard"
           }
         ]
       },
       "editable": True,
       "fiscalYearStartMonth": 0,
       "graphTooltip": 0,
       "id": None,
       "links": [],
       "liveNow": False,
       "panels": panels,
       "refresh": "5s",
       "schemaVersion": 39,
       "tags": [],
       "templating": {
         "list": []
       },
       "time": {
         "from": "now-6h",
         "to": "now"
       },
       "timepicker": {},
       "timezone": "",
       "title": dashboard_name,
       "uid": "",
       "version": 1,
       "weekStart": ""
     }
    return dashboard

   
    # link_ids = add_nodes_and_links(diagram, nodes, positions, links, node_graphlevels, no_links=no_links, layout=layout, verbose=verbose, base_style=base_style, link_style=link_style, custom_styles=custom_styles, icon_to_group_mapping=icon_to_group_mapping)

    # # If output_file is not provided, generate it from input_file
    # if not output_file:
    #     output_file = os.path.splitext(input_file)[0] + ".drawio"
    #     gf_file= os.path.splitext(input_file)[0] + ".grafana.json"
        
    # output_folder = os.path.dirname(output_file) or "."
    # output_filename = os.path.basename(output_file)
    # output_gf_filename = os.path.basename(gf_file)
    # os.makedirs(output_folder, exist_ok=True)

    # diagram.dump_file(filename=output_filename, folder=output_folder)
    # print("Saved file to:", output_file)
    # create_grafana_dashboard(diagram,dashboard_filename=output_gf_filename,link_list=link_ids)

def main(input_file, output_file, theme, include_unlinked_nodes=False, no_links=False, layout='vertical', verbose=False, gf_dashboard=False):
    """
    Generates a diagram from a given topology definition file, organizing and displaying nodes and links.
    
    Processes an input YAML file containing node and link definitions, extracts relevant information,
    and applies logic to determine node positions and connectivity. The function supports filtering out unlinked nodes,
    optionally excluding links, choosing the layout orientation, and toggling verbose output for detailed processing logs.
    """
    try:
        with open(input_file, 'r') as file:
            containerlab_data = yaml.safe_load(file)
    except FileNotFoundError:
        error_message = f"Error: The specified clab file '{input_file}' does not exist."
        print(error_message)
        exit()
    except Exception as e:
        error_message = f"An error occurred while loading the config: {e}"
        print(error_message)
        exit()

    if 'grafana' in theme.lower():
        no_links = True

    if theme in ['nokia_bright', 'nokia_dark', 'grafana_dark']:
        config_path = os.path.join(script_dir, f'styles/{theme}.yaml')
    else:
        # Assume the user has provided a custom path
        config_path = theme

    # Load styles
    styles = load_styles_from_config(config_path)

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

    #Calculate the diagram size based on the positions of the nodes
    min_x = min(position[0] for position in positions.values())
    min_y = min(position[1] for position in positions.values())
    max_x = max(position[0] for position in positions.values())
    max_y = max(position[1] for position in positions.values())

    max_size_x = max_x - min_x + 2 * 150
    max_size_y = max_y - min_y + 2 * 150

    if styles['pagew'] == "auto":
        styles['pagew'] = max_size_x
    if styles['pageh'] == "auto":
        styles['pageh'] = max_size_y

    # Adjust positions to ensure the smallest x and y are at least 0
    positions = {node: (x - min_x + 100, y - min_y + 100) for node, (x, y) in positions.items()}

    # Create a draw.io diagram instance
    diagram = CustomDrawioDiagram(styles=styles)

    # Add a diagram page
    diagram.add_diagram("Network Topology")

    # Add nodes to the diagram
    add_nodes(diagram, nodes, positions, node_graphlevels, styles=styles)

    # Add links to the diagram
    add_links(diagram, links, positions, node_graphlevels, styles=styles, no_links=no_links, layout=layout, verbose=verbose)
    # Add connector nodes for each link
    if 'grafana' in theme.lower():
        connector_links = add_connector_nodes(diagram, nodes, links, positions, styles=styles, verbose=verbose)
        add_links_with_connectors(diagram, connector_links, link_style=styles['link_style'], verbose=verbose)
        gf_dashboard = True

    # If output_file is not provided, generate it from input_file
    if not output_file:
        output_file = os.path.splitext(input_file)[0] + ".drawio"
        
    output_folder = os.path.dirname(output_file) or "."
    output_filename = os.path.basename(output_file)
    os.makedirs(output_folder, exist_ok=True)

    diagram.dump_file(filename=output_filename, folder=output_folder)

    print("Saved file to:", output_file)
    if gf_dashboard:
        output_gf_filename = os.path.basename(os.path.splitext(input_file)[0] + ".grafana.json")
        if verbose:
           print(connector_links)
        link_id_list = []
        for link in connector_links:
            link_id_list.append(f"link_id:{link['link_id']}")
        create_grafana_dashboard(diagram,dashboard_filename=output_gf_filename,link_list=link_id_list)


def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate a topology diagram from a containerlab YAML or draw.io XML file.')
    parser.add_argument('-i', '--input', required=True, help='The filename of the input file (containerlab YAML for diagram generation).')
    parser.add_argument('-o', '--output', required=False, help='The output file path for the generated diagram (draw.io format).')
    parser.add_argument('-g', '--gf_dashboard',default=False, required=False, help='Generate Grafana Dashboard Flag.')
    parser.add_argument('--include-unlinked-nodes', action='store_true', help='Include nodes without any links in the topology diagram')
    parser.add_argument('--no-links', action='store_true', help='Do not draw links between nodes in the topology diagram')
    parser.add_argument('--layout', type=str, default='vertical', choices=['vertical', 'horizontal'], help='Specify the layout of the topology diagram (vertical or horizontal)')
    parser.add_argument('--theme', default='nokia_bright', help='Specify the theme for the diagram (nokia_bright, nokia_dark, grafana_dark) or the path to a custom style config file.')  
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output for debugging purposes')  
    return parser.parse_args()
    
if __name__ == "__main__":
    args = parse_arguments()

    script_dir = os.path.dirname(__file__)

    main(args.input, args.output, args.theme, args.include_unlinked_nodes, args.no_links, args.layout, args.verbose, args.gf_dashboard)


