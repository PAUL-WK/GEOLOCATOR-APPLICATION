import streamlit as st
import osmnx as ox
import networkx as nx
import leafmap.foliumap as leafmap
from streamlit_geolocation import streamlit_geolocation
import math
from time import sleep

# Set up the Streamlit page
st.set_page_config(page_title="Campus Navigator", layout="wide")

# Page title
st.title("Dedan Kimathi University Campus Navigator")

# Initialize session state for navigation
if 'navigating' not in st.session_state:
    st.session_state.navigating = False
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0

# Define predefined locations (lat, lon) for key buildings or points
locations = {
    "Main Entrance": (-0.3966, 36.9594),
    "Lecture Hall A": (-0.3972, 36.9601),
    "Library": (-0.3958, 36.9599),
    "Admin Building": (-0.3964, 36.9589),
    "Sports Complex": (-0.3970, 36.9585),
}

# Sidebar
st.sidebar.title("Navigation Tools")
st.sidebar.info("Use the tools below to navigate around the campus.")

@st.cache_data
def fetch_osm_road_network(center, radius=1000):
    try:
        road_network = ox.graph_from_point(center, dist=radius, network_type="all")
        return road_network
    except Exception as e:
        st.error(f"Error fetching road network: {e}")
        return None

def get_bearing(point1, point2):
    lat1, lon1 = point1
    lat2, lon2 = point2
    
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)
    
    d_lon = lon2 - lon1
    
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = math.atan2(y, x)
    
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360
    
    return bearing

def get_turn_direction(current_bearing, next_bearing):
    """Determine if the user needs to turn and in which direction."""
    angle_diff = (next_bearing - current_bearing + 360) % 360
    
    if angle_diff < 30 or angle_diff > 330:
        return "Continue straight"
    elif 30 <= angle_diff < 150:
        return "Turn right"
    elif 150 <= angle_diff < 210:
        return "Make a U-turn"
    else:
        return "Turn left"

def calculate_distance(point1, point2):
    """Calculate distance between two points in meters."""
    from math import sin, cos, sqrt, atan2, radians
    
    R = 6371000  # Earth's radius in meters
    
    lat1, lon1 = radians(point1[0]), radians(point1[1])
    lat2, lon2 = radians(point2[0]), radians(point2[1])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    return distance

def generate_turn_by_turn(road_network, route, current_position):
    """Generate turn-by-turn directions based on current position."""
    directions = []
    
    if len(route) < 2:
        return directions
    
    # Find the nearest point on the route to current position
    current_node = min(route, key=lambda node: calculate_distance(
        current_position,
        (road_network.nodes[node]['y'], road_network.nodes[node]['x'])
    ))
    
    current_index = route.index(current_node)
    
    # Generate directions for remaining route
    for i in range(current_index, len(route) - 1):
        current_node = route[i]
        next_node = route[i + 1]
        
        current_point = (road_network.nodes[current_node]['y'], road_network.nodes[current_node]['x'])
        next_point = (road_network.nodes[next_node]['y'], road_network.nodes[next_node]['x'])
        
        # Calculate bearings
        if i == current_index:
            current_bearing = get_bearing(current_position, next_point)
        else:
            prev_point = (road_network.nodes[route[i-1]]['y'], road_network.nodes[route[i-1]]['x'])
            current_bearing = get_bearing(prev_point, current_point)
        next_bearing = get_bearing(current_point, next_point)
        
        # Get turn direction
        turn = get_turn_direction(current_bearing, next_bearing)
        
        # Calculate distance
        distance = calculate_distance(current_point, next_point)
        
        # Create direction step
        step = f"{turn} and continue for {int(distance)} meters"
        directions.append(step)
    
    return directions

def calculate_route(start_coords, end_coords, road_network):
    try:
        nearest_start = min(road_network.nodes(), 
                            key=lambda node: ((road_network.nodes[node]['y'] - start_coords[0])**2 + 
                                              (road_network.nodes[node]['x'] - start_coords[1])**2))
        
        nearest_end = min(road_network.nodes(), 
                          key=lambda node: ((road_network.nodes[node]['y'] - end_coords[0])**2 + 
                                            (road_network.nodes[node]['x'] - end_coords[1])**2))
        
        route = nx.shortest_path(road_network, nearest_start, nearest_end, weight="length")
        return route
    except Exception as e:
        st.error(f"Error calculating route: {e}")
        return None

def plot_route(route, road_network, m, start_coords, end_coords, start_location, end_location):
    try:
        route_edges = []
        for u, v in zip(route[:-1], route[1:]):
            route_edges.append((u, v, 0))
        
        edges_gdf = ox.graph_to_gdfs(road_network, nodes=False, edges=True)
        route_edges_gdf = edges_gdf.loc[route_edges]
        
        m.add_gdf(route_edges_gdf, layer_name="Route", style={"color": "red", "weight": 4})
        
        m.add_marker(location=start_coords, popup=f"Start: {start_location}")
        m.add_marker(location=end_coords, popup=f"End: {end_location}")
    except Exception as e:
        st.error(f"Error plotting route: {e}")

def toggle_navigation():
    st.session_state.navigating = not st.session_state.navigating
    st.session_state.current_step = 0

location = streamlit_geolocation()
if location:
    user_lat, user_lon = location['latitude'], location['longitude']

st.sidebar.write(f"Current location: {user_lat:.3f}, {user_lon:.3f}")

def main():
    st.sidebar.subheader("Choose your starting and ending points")
    start_location = (user_lat, user_lon)
    end_location = st.sidebar.selectbox("Select Destination", list(locations.keys()))

    start_coords = start_location
    end_coords = locations[end_location]

    road_network = fetch_osm_road_network(start_coords, radius=1000)
    
    if road_network is None:
        st.error("Could not fetch road network. Please check your internet connection.")
        return

    route = calculate_route(start_coords, end_coords, road_network)
    
    if route is None:
        st.error("Could not calculate route. Possible reasons: \n- No connected path between points\n- Network too small")
        return

    # Navigation control
    if st.sidebar.button("Start/Stop Navigation", on_click=toggle_navigation):
        pass

    # Display navigation status
    st.sidebar.write("Navigation Status:", "Active" if st.session_state.navigating else "Inactive")

    # Generate and display directions
    if st.session_state.navigating:
        current_position = (user_lat, user_lon)
        directions = generate_turn_by_turn(road_network, route, current_position)
        
        st.sidebar.subheader("Current Navigation")
        if directions:
            # Display current step with highlighting
            st.sidebar.markdown(f"**Next step:** {directions[st.session_state.current_step]}")
            
            # Display upcoming steps
            if len(directions) > st.session_state.current_step + 1:
                st.sidebar.subheader("Upcoming Steps")
                for i, direction in enumerate(directions[st.session_state.current_step + 1:], st.session_state.current_step + 1):
                    st.sidebar.write(f"{i+1}. {direction}")

    # Initialize map
    m = leafmap.Map(center=start_coords, zoom=17)
    m.add_basemap("OpenStreetMap")

    # Plot route
    plot_route(route, road_network, m, start_coords, end_coords, start_location, end_location)

    # Display map
    st.subheader("Interactive Map with Route")
    m.to_streamlit(height=600)

    st.subheader(f"Route from Current Location to {end_location}")
    st.write("Follow the turn-by-turn directions in the sidebar.")

if __name__ == "__main__":
    main()