'''
this code is a next attempt to create image generation from scratch

generate traffic - done
change weather and time of day - done
loop though maps - done
spawn a hero - done - always first car in the list
point spectator to it - done
attach sensors - done (may need to remove 4th dim)
create map capture - done
getting stuck workaround
arrange image saving and count

'''

import sys
from numpy import random
import numpy as np
import math
import logging
import os
import glob
import re
import cv2
import pygame
import hashlib
import time

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla
from carla import TrafficLightState as tls

MAPS = ["Town01", "Town02", "Town03", "Town04", "Town05", "Town10HD"]
DISTANCE_SPECTATOR = 5
#camera mount offset on the car to mimic Tesla Model3
CAMERA_POS_Z = 1.3 
CAMERA_POS_X = 1.4 

CAM_W = '640'
CAM_H = '480'

NO_RENDERING = True

MAP_FOLDER = 'C://SelfDrive//2025 Map from vision//map_img//'
IMAGE_FOLDER = 'C://SelfDrive//2025 Map from vision//img//'

MAP_CAPTURE_CROP_FACTOR = 1.5 # by what factor we crop height and width of a map to save an image of it  


PIXELS_FROM_MAP_BOTTOM = 210 #number of most low rows of map image to locate the car in
PIXELS_FROM_CENTRE_SIDEWISE = 10 #number of pixels to take to the sides off the centre fo locating the car shape

CROP_MAP_PIXELS_Y = 264
CROP_MAP_PIXELS_X = 240

MIN_MOVE_BETWEEN_IMAGES = 2 #meters required to move before taking next image


# Colors

# We will use the color palette used in Tango Desktop Project (Each color is indexed depending on brightness level)
# See: https://en.wikipedia.org/wiki/Tango_Desktop_Project

COLOR_BUTTER_0 = pygame.Color(252, 233, 79)
COLOR_BUTTER_1 = pygame.Color(237, 212, 0)
COLOR_BUTTER_2 = pygame.Color(196, 160, 0)

COLOR_ORANGE_0 = pygame.Color(252, 175, 62)
COLOR_ORANGE_1 = pygame.Color(245, 121, 0)
COLOR_ORANGE_2 = pygame.Color(209, 92, 0)

COLOR_CHOCOLATE_0 = pygame.Color(233, 185, 110)
COLOR_CHOCOLATE_1 = pygame.Color(193, 125, 17)
COLOR_CHOCOLATE_2 = pygame.Color(143, 89, 2)

COLOR_CHAMELEON_0 = pygame.Color(138, 226, 52)
COLOR_CHAMELEON_1 = pygame.Color(115, 210, 22)
COLOR_CHAMELEON_2 = pygame.Color(78, 154, 6)

COLOR_SKY_BLUE_0 = pygame.Color(114, 159, 207)
COLOR_SKY_BLUE_1 = pygame.Color(52, 101, 164)
COLOR_SKY_BLUE_2 = pygame.Color(32, 74, 135)

COLOR_PLUM_0 = pygame.Color(173, 127, 168)
COLOR_PLUM_1 = pygame.Color(117, 80, 123)
COLOR_PLUM_2 = pygame.Color(92, 53, 102)

COLOR_SCARLET_RED_0 = pygame.Color(239, 41, 41)
COLOR_SCARLET_RED_1 = pygame.Color(204, 0, 0)
COLOR_SCARLET_RED_2 = pygame.Color(164, 0, 0)

COLOR_ALUMINIUM_0 = pygame.Color(238, 238, 236)
COLOR_ALUMINIUM_1 = pygame.Color(211, 215, 207)
COLOR_ALUMINIUM_2 = pygame.Color(186, 189, 182)
COLOR_ALUMINIUM_3 = pygame.Color(136, 138, 133)
COLOR_ALUMINIUM_4 = pygame.Color(85, 87, 83)
COLOR_ALUMINIUM_4_5 = pygame.Color(66, 62, 64)
COLOR_ALUMINIUM_5 = pygame.Color(46, 52, 54)


COLOR_WHITE = pygame.Color(255, 255, 255)
COLOR_BLACK = pygame.Color(0, 0, 0)


PIXELS_PER_METER = 12

MAP_DEFAULT_SCALE = 0.1
HERO_DEFAULT_SCALE = 1.0

PIXELS_AHEAD_VEHICLE = 120


def sem_callback(image,data_dict):
    image.convert(carla.ColorConverter.CityScapesPalette)
    data_dict['sem_image'] = np.reshape(np.copy(image.raw_data),(image.height,image.width,4))
    
def rgb_callback(image,data_dict):
    data_dict['rgb_image'] = np.reshape(np.copy(image.raw_data),(image.height,image.width,4))

def calculate_sides(hypotenuse, angle):

  # Convert the angle to radians
  angle_radians = math.radians(angle)

  # Calculate the opposite side using the sine function
  opposite_side = hypotenuse * math.sin(angle_radians)

  # Calculate the adjacent side using the cosine function
  adjacent_side = hypotenuse * math.cos(angle_radians)

  return opposite_side, adjacent_side

def adjust_spectator():
    '''
    optional function to make spectator view using above function
    '''
    vehicle_transform = sim_world.get_actors(world.vehicles_list)[0].get_transform()
    y,x = calculate_sides(DISTANCE_SPECTATOR, vehicle_transform.rotation.yaw )
    spectator_pos = carla.Transform(vehicle_transform.location + carla.Location(x=-x,y=-y,z=5 ),
                                            carla.Rotation( yaw = vehicle_transform.rotation.yaw,pitch = -25))
    spectator.set_transform(spectator_pos)  
 

def get_actor_blueprints(world, filter, generation):
    bps = world.get_blueprint_library().filter(filter)

    if generation.lower() == "all":
        return bps

    # If the filter returns only one bp, we assume that this one needed
    # and therefore, we ignore the generation
    if len(bps) == 1:
        return bps

    try:
        int_generation = int(generation)
        # Check if generation is in available generations
        if int_generation in [1, 2, 3]:
            bps = [x for x in bps if int(x.get_attribute('generation')) == int_generation]
            return bps
        else:
            print("   Warning! Actor Generation is not valid. No actor will be spawned.")
            return []
    except:
        print("   Warning! Actor Generation is not valid. No actor will be spawned.")
        return []

def find_weather_presets():
    rgx = re.compile('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)')
    name = lambda x: ' '.join(m.group(0) for m in rgx.finditer(x))
    presets = [x for x in dir(carla.WeatherParameters) if re.match('[A-Z].+', x)]
    return [(getattr(carla.WeatherParameters, x), name(x)) for x in presets]

class TrafficLightSurfaces(object):
    """Holds the surfaces (scaled and rotated) for painting traffic lights"""

    def __init__(self):
        def make_surface(tl):
            """Draws a traffic light, which is composed of a dark background surface with 3 circles that indicate its color depending on the state"""
            w = 40
            surface = pygame.Surface((w, 3 * w), pygame.SRCALPHA)
            surface.fill(COLOR_ALUMINIUM_5 if tl != 'h' else COLOR_ORANGE_2)
            if tl != 'h':
                hw = int(w / 2)
                off = COLOR_ALUMINIUM_4
                red = COLOR_SCARLET_RED_0
                yellow = COLOR_BUTTER_0
                green = COLOR_CHAMELEON_0

                # Draws the corresponding color if is on, otherwise it will be gray if its off
                pygame.draw.circle(surface, red if tl == tls.Red else off, (hw, hw), int(0.4 * w))
                pygame.draw.circle(surface, yellow if tl == tls.Yellow else off, (hw, w + hw), int(0.4 * w))
                pygame.draw.circle(surface, green if tl == tls.Green else off, (hw, 2 * w + hw), int(0.4 * w))

            return pygame.transform.smoothscale(surface, (15, 45) if tl != 'h' else (19, 49))

        self._original_surfaces = {
            'h': make_surface('h'),
            tls.Red: make_surface(tls.Red),
            tls.Yellow: make_surface(tls.Yellow),
            tls.Green: make_surface(tls.Green),
            tls.Off: make_surface(tls.Off),
            tls.Unknown: make_surface(tls.Unknown)
        }
        self.surfaces = dict(self._original_surfaces)

    def rotozoom(self, angle, scale):
        """Rotates and scales the traffic light surface"""
        for key, surface in self._original_surfaces.items():
            self.surfaces[key] = pygame.transform.rotozoom(surface, angle, scale)


class MapImage(object):
    """Class encharged of rendering a 2D image from top view of a carla world. Please note that a cache system is used, so if the OpenDrive content
    of a Carla town has not changed, it will read and use the stored image if it was rendered in a previous execution"""

    def __init__(self, carla_world, carla_map, pixels_per_meter, show_triggers, show_connections, show_spawn_points):
        """ Renders the map image generated based on the world, its map and additional flags that provide extra information about the road network"""
        self._pixels_per_meter = pixels_per_meter
        self.scale = 1.0
        self.show_triggers = show_triggers
        self.show_connections = show_connections
        self.show_spawn_points = show_spawn_points

        waypoints = carla_map.generate_waypoints(2)
        margin = 50
        max_x = max(waypoints, key=lambda x: x.transform.location.x).transform.location.x + margin
        max_y = max(waypoints, key=lambda x: x.transform.location.y).transform.location.y + margin
        min_x = min(waypoints, key=lambda x: x.transform.location.x).transform.location.x - margin
        min_y = min(waypoints, key=lambda x: x.transform.location.y).transform.location.y - margin

        self.width = max(max_x - min_x, max_y - min_y)
        self._world_offset = (min_x, min_y)

        # Maximum size of a Pygame surface
        width_in_pixels = (1 << 14) - 1

        # Adapt Pixels per meter to make world fit in surface
        surface_pixel_per_meter = int(width_in_pixels / self.width)
        if surface_pixel_per_meter > PIXELS_PER_METER:
            surface_pixel_per_meter = PIXELS_PER_METER

        self._pixels_per_meter = surface_pixel_per_meter
        width_in_pixels = int(self._pixels_per_meter * self.width)
        
        self.big_map_surface = pygame.Surface((width_in_pixels, width_in_pixels)).convert()
        
        # Load OpenDrive content
        opendrive_content = carla_map.to_opendrive()

        # Get hash based on content
        hash_func = hashlib.sha1()
        hash_func.update(opendrive_content.encode("UTF-8"))
        opendrive_hash = str(hash_func.hexdigest())

        # Build path for saving or loading the cached rendered map
        filename = carla_map.name.split('/')[-1] + "_" + opendrive_hash + ".tga"
        dirname = os.path.join("cache", "no_rendering_mode")
        full_path = str(os.path.join(dirname, filename))
        print('path to cache:',full_path)

        if os.path.isfile(full_path):
            # Load Image
            self.big_map_surface = pygame.image.load(full_path)
        else:
            # Render map
            self.draw_road_map(
                self.big_map_surface,
                carla_world,
                carla_map,
                self.world_to_pixel,
                self.world_to_pixel_width)

            # If folders path does not exist, create it
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            # Remove files if selected town had a previous version saved
            list_filenames = glob.glob(os.path.join(dirname, carla_map.name) + "*")
            for town_filename in list_filenames:
                os.remove(town_filename)

            # Save rendered map for next executions of same map
            pygame.image.save(self.big_map_surface, full_path)

        self.surface = self.big_map_surface

    def draw_road_map(self, map_surface, carla_world, carla_map, world_to_pixel, world_to_pixel_width):
        """Draws all the roads, including lane markings, arrows and traffic signs"""
        map_surface.fill(COLOR_ALUMINIUM_4)
        precision = 0.05

        def lane_marking_color_to_tango(lane_marking_color):
            """Maps the lane marking color enum specified in PythonAPI to a Tango Color"""
            tango_color = COLOR_BLACK

            if lane_marking_color == carla.LaneMarkingColor.White:
                tango_color = COLOR_ALUMINIUM_2

            elif lane_marking_color == carla.LaneMarkingColor.Blue:
                tango_color = COLOR_SKY_BLUE_0

            elif lane_marking_color == carla.LaneMarkingColor.Green:
                tango_color = COLOR_CHAMELEON_0

            elif lane_marking_color == carla.LaneMarkingColor.Red:
                tango_color = COLOR_SCARLET_RED_0

            elif lane_marking_color == carla.LaneMarkingColor.Yellow:
                tango_color = COLOR_ORANGE_0

            return tango_color

        def draw_solid_line(surface, color, closed, points, width):
            """Draws solid lines in a surface given a set of points, width and color"""
            if len(points) >= 2:
                pygame.draw.lines(surface, color, closed, points, width)

        def draw_broken_line(surface, color, closed, points, width):
            """Draws broken lines in a surface given a set of points, width and color"""
            # Select which lines are going to be rendered from the set of lines
            broken_lines = [x for n, x in enumerate(zip(*(iter(points),) * 20)) if n % 3 == 0]

            # Draw selected lines
            for line in broken_lines:
                pygame.draw.lines(surface, color, closed, line, width)

        def get_lane_markings(lane_marking_type, lane_marking_color, waypoints, sign):
            """For multiple lane marking types (SolidSolid, BrokenSolid, SolidBroken and BrokenBroken), it converts them
             as a combination of Broken and Solid lines"""
            margin = 0.25
            marking_1 = [world_to_pixel(lateral_shift(w.transform, sign * w.lane_width * 0.5)) for w in waypoints]
            if lane_marking_type == carla.LaneMarkingType.Broken or (lane_marking_type == carla.LaneMarkingType.Solid):
                return [(lane_marking_type, lane_marking_color, marking_1)]
            else:
                marking_2 = [world_to_pixel(lateral_shift(w.transform,
                                                          sign * (w.lane_width * 0.5 + margin * 2))) for w in waypoints]
                if lane_marking_type == carla.LaneMarkingType.SolidBroken:
                    return [(carla.LaneMarkingType.Broken, lane_marking_color, marking_1),
                            (carla.LaneMarkingType.Solid, lane_marking_color, marking_2)]
                elif lane_marking_type == carla.LaneMarkingType.BrokenSolid:
                    return [(carla.LaneMarkingType.Solid, lane_marking_color, marking_1),
                            (carla.LaneMarkingType.Broken, lane_marking_color, marking_2)]
                elif lane_marking_type == carla.LaneMarkingType.BrokenBroken:
                    return [(carla.LaneMarkingType.Broken, lane_marking_color, marking_1),
                            (carla.LaneMarkingType.Broken, lane_marking_color, marking_2)]
                elif lane_marking_type == carla.LaneMarkingType.SolidSolid:
                    return [(carla.LaneMarkingType.Solid, lane_marking_color, marking_1),
                            (carla.LaneMarkingType.Solid, lane_marking_color, marking_2)]

            return [(carla.LaneMarkingType.NONE, carla.LaneMarkingColor.Other, [])]

        def draw_lane(surface, lane, color):
            """Renders a single lane in a surface and with a specified color"""
            for side in lane:
                lane_left_side = [lateral_shift(w.transform, -w.lane_width * 0.5) for w in side]
                lane_right_side = [lateral_shift(w.transform, w.lane_width * 0.5) for w in side]

                polygon = lane_left_side + [x for x in reversed(lane_right_side)]
                polygon = [world_to_pixel(x) for x in polygon]

                if len(polygon) > 2:
                    pygame.draw.polygon(surface, color, polygon, 5)
                    pygame.draw.polygon(surface, color, polygon)

        def draw_lane_marking(surface, waypoints):
            """Draws the left and right side of lane markings"""
            # Left Side
            draw_lane_marking_single_side(surface, waypoints[0], -1)

            # Right Side
            draw_lane_marking_single_side(surface, waypoints[1], 1)

        def draw_lane_marking_single_side(surface, waypoints, sign):
            """Draws the lane marking given a set of waypoints and decides whether drawing the right or left side of
            the waypoint based on the sign parameter"""
            lane_marking = None

            marking_type = carla.LaneMarkingType.NONE
            previous_marking_type = carla.LaneMarkingType.NONE

            marking_color = carla.LaneMarkingColor.Other
            previous_marking_color = carla.LaneMarkingColor.Other

            markings_list = []
            temp_waypoints = []
            current_lane_marking = carla.LaneMarkingType.NONE
            for sample in waypoints:
                lane_marking = sample.left_lane_marking if sign < 0 else sample.right_lane_marking

                if lane_marking is None:
                    continue

                marking_type = lane_marking.type
                marking_color = lane_marking.color

                if current_lane_marking != marking_type:
                    # Get the list of lane markings to draw
                    markings = get_lane_markings(
                        previous_marking_type,
                        lane_marking_color_to_tango(previous_marking_color),
                        temp_waypoints,
                        sign)
                    current_lane_marking = marking_type

                    # Append each lane marking in the list
                    for marking in markings:
                        markings_list.append(marking)

                    temp_waypoints = temp_waypoints[-1:]

                else:
                    temp_waypoints.append((sample))
                    previous_marking_type = marking_type
                    previous_marking_color = marking_color

            # Add last marking
            last_markings = get_lane_markings(
                previous_marking_type,
                lane_marking_color_to_tango(previous_marking_color),
                temp_waypoints,
                sign)
            for marking in last_markings:
                markings_list.append(marking)

            # Once the lane markings have been simplified to Solid or Broken lines, we draw them
            for markings in markings_list:
                if markings[0] == carla.LaneMarkingType.Solid:
                    draw_solid_line(surface, markings[1], False, markings[2], 2)
                elif markings[0] == carla.LaneMarkingType.Broken:
                    draw_broken_line(surface, markings[1], False, markings[2], 2)

        def draw_arrow(surface, transform, color=COLOR_ALUMINIUM_2):
            """ Draws an arrow with a specified color given a transform"""
            transform.rotation.yaw += 180
            forward = transform.get_forward_vector()
            transform.rotation.yaw += 90
            right_dir = transform.get_forward_vector()
            end = transform.location
            start = end - 2.0 * forward
            right = start + 0.8 * forward + 0.4 * right_dir
            left = start + 0.8 * forward - 0.4 * right_dir

            # Draw lines
            pygame.draw.lines(surface, color, False, [world_to_pixel(x) for x in [start, end]], 4)
            pygame.draw.lines(surface, color, False, [world_to_pixel(x) for x in [left, start, right]], 4)

        def draw_traffic_signs(surface, font_surface, actor, color=COLOR_ALUMINIUM_2, trigger_color=COLOR_PLUM_0):
            """Draw stop traffic signs and its bounding box if enabled"""
            transform = actor.get_transform()
            waypoint = carla_map.get_waypoint(transform.location)

            angle = -waypoint.transform.rotation.yaw - 90.0
            font_surface = pygame.transform.rotate(font_surface, angle)
            pixel_pos = world_to_pixel(waypoint.transform.location)
            offset = font_surface.get_rect(center=(pixel_pos[0], pixel_pos[1]))
            surface.blit(font_surface, offset)

            # Draw line in front of stop
            forward_vector = carla.Location(waypoint.transform.get_forward_vector())
            left_vector = carla.Location(-forward_vector.y, forward_vector.x,
                                         forward_vector.z) * waypoint.lane_width / 2 * 0.7

            line = [(waypoint.transform.location + (forward_vector * 1.5) + (left_vector)),
                    (waypoint.transform.location + (forward_vector * 1.5) - (left_vector))]

            line_pixel = [world_to_pixel(p) for p in line]
            pygame.draw.lines(surface, color, True, line_pixel, 2)

            # Draw bounding box of the stop trigger
            if self.show_triggers:
                corners = Util.get_bounding_box(actor)
                corners = [world_to_pixel(p) for p in corners]
                pygame.draw.lines(surface, trigger_color, True, corners, 2)

        def lateral_shift(transform, shift):
            """Makes a lateral shift of the forward vector of a transform"""
            transform.rotation.yaw += 90
            return transform.location + shift * transform.get_forward_vector()

        def draw_topology(carla_topology, index):
            """ Draws traffic signs and the roads network with sidewalks, parking and shoulders by generating waypoints"""
            topology = [x[index] for x in carla_topology]
            topology = sorted(topology, key=lambda w: w.transform.location.z)
            set_waypoints = []
            for waypoint in topology:
                waypoints = [waypoint]

                # Generate waypoints of a road id. Stop when road id differs
                nxt = waypoint.next(precision)
                if len(nxt) > 0:
                    nxt = nxt[0]
                    while nxt.road_id == waypoint.road_id:
                        waypoints.append(nxt)
                        nxt = nxt.next(precision)
                        if len(nxt) > 0:
                            nxt = nxt[0]
                        else:
                            break
                set_waypoints.append(waypoints)

                # Draw Shoulders, Parkings and Sidewalks
                PARKING_COLOR = COLOR_ALUMINIUM_4_5
                SHOULDER_COLOR = COLOR_ALUMINIUM_5
                SIDEWALK_COLOR = COLOR_ALUMINIUM_3

                shoulder = [[], []]
                parking = [[], []]
                sidewalk = [[], []]

                for w in waypoints:
                    # Classify lane types until there are no waypoints by going left
                    l = w.get_left_lane()
                    while l and l.lane_type != carla.LaneType.Driving:

                        if l.lane_type == carla.LaneType.Shoulder:
                            shoulder[0].append(l)

                        if l.lane_type == carla.LaneType.Parking:
                            parking[0].append(l)

                        if l.lane_type == carla.LaneType.Sidewalk:
                            sidewalk[0].append(l)

                        l = l.get_left_lane()

                    # Classify lane types until there are no waypoints by going right
                    r = w.get_right_lane()
                    while r and r.lane_type != carla.LaneType.Driving:

                        if r.lane_type == carla.LaneType.Shoulder:
                            shoulder[1].append(r)

                        if r.lane_type == carla.LaneType.Parking:
                            parking[1].append(r)

                        if r.lane_type == carla.LaneType.Sidewalk:
                            sidewalk[1].append(r)

                        r = r.get_right_lane()

                # Draw classified lane types
                draw_lane(map_surface, shoulder, SHOULDER_COLOR)
                draw_lane(map_surface, parking, PARKING_COLOR)
                draw_lane(map_surface, sidewalk, SIDEWALK_COLOR)

            # Draw Roads
            for waypoints in set_waypoints:
                waypoint = waypoints[0]
                road_left_side = [lateral_shift(w.transform, -w.lane_width * 0.5) for w in waypoints]
                road_right_side = [lateral_shift(w.transform, w.lane_width * 0.5) for w in waypoints]

                polygon = road_left_side + [x for x in reversed(road_right_side)]
                polygon = [world_to_pixel(x) for x in polygon]

                if len(polygon) > 2:
                    pygame.draw.polygon(map_surface, COLOR_ALUMINIUM_5, polygon, 5)
                    pygame.draw.polygon(map_surface, COLOR_ALUMINIUM_5, polygon)

                # Draw Lane Markings and Arrows
                if not waypoint.is_junction:
                    draw_lane_marking(map_surface, [waypoints, waypoints])
                    for n, wp in enumerate(waypoints):
                        if ((n + 1) % 400) == 0:
                            draw_arrow(map_surface, wp.transform)

        topology = carla_map.get_topology()
        draw_topology(topology, 0)

        if self.show_spawn_points:
            for sp in carla_map.get_spawn_points():
                draw_arrow(map_surface, sp, color=COLOR_CHOCOLATE_0)

        if self.show_connections:
            dist = 1.5

            def to_pixel(wp): return world_to_pixel(wp.transform.location)
            for wp in carla_map.generate_waypoints(dist):
                col = (0, 255, 255) if wp.is_junction else (0, 255, 0)
                for nxt in wp.next(dist):
                    pygame.draw.line(map_surface, col, to_pixel(wp), to_pixel(nxt), 2)
                if wp.lane_change & carla.LaneChange.Right:
                    r = wp.get_right_lane()
                    if r and r.lane_type == carla.LaneType.Driving:
                        pygame.draw.line(map_surface, col, to_pixel(wp), to_pixel(r), 2)
                if wp.lane_change & carla.LaneChange.Left:
                    l = wp.get_left_lane()
                    if l and l.lane_type == carla.LaneType.Driving:
                        pygame.draw.line(map_surface, col, to_pixel(wp), to_pixel(l), 2)

        actors = carla_world.get_actors()

        # Find and Draw Traffic Signs: Stops and Yields
        font_size = world_to_pixel_width(1)
        font = pygame.font.SysFont('Arial', font_size, True)

        stops = [actor for actor in actors if 'stop' in actor.type_id]
        yields = [actor for actor in actors if 'yield' in actor.type_id]

        stop_font_surface = font.render("STOP", False, COLOR_ALUMINIUM_2)
        stop_font_surface = pygame.transform.scale(
            stop_font_surface, (stop_font_surface.get_width(), stop_font_surface.get_height() * 2))

        yield_font_surface = font.render("YIELD", False, COLOR_ALUMINIUM_2)
        yield_font_surface = pygame.transform.scale(
            yield_font_surface, (yield_font_surface.get_width(), yield_font_surface.get_height() * 2))

        for ts_stop in stops:
            draw_traffic_signs(map_surface, stop_font_surface, ts_stop, trigger_color=COLOR_SCARLET_RED_1)

        for ts_yield in yields:
            draw_traffic_signs(map_surface, yield_font_surface, ts_yield, trigger_color=COLOR_ORANGE_1)

    def world_to_pixel(self, location, offset=(0, 0)):
        """Converts the world coordinates to pixel coordinates"""
        x = self.scale * self._pixels_per_meter * (location.x - self._world_offset[0])
        y = self.scale * self._pixels_per_meter * (location.y - self._world_offset[1])
        return [int(x - offset[0]), int(y - offset[1])]

    def world_to_pixel_width(self, width):
        """Converts the world units to pixel units"""
        return int(self.scale * self._pixels_per_meter * width)

    def scale_map(self, scale):
        """Scales the map surface"""
        if scale != self.scale:
            self.scale = scale
            width = int(self.big_map_surface.get_width() * self.scale)
            self.surface = pygame.transform.smoothscale(self.big_map_surface, (width, width))

class Util(object):

    @staticmethod
    def blits(destination_surface, source_surfaces, rect=None, blend_mode=0):
        """Function that renders the all the source surfaces in a destination source"""
        for surface in source_surfaces:
            destination_surface.blit(surface[0], surface[1], rect, blend_mode)

    @staticmethod
    def length(v):
        """Returns the length of a vector"""
        return math.sqrt(v.x**2 + v.y**2 + v.z**2)

    @staticmethod
    def get_bounding_box(actor):
        """Gets the bounding box corners of an actor in world space"""
        bb = actor.trigger_volume.extent
        corners = [carla.Location(x=-bb.x, y=-bb.y),
                   carla.Location(x=bb.x, y=-bb.y),
                   carla.Location(x=bb.x, y=bb.y),
                   carla.Location(x=-bb.x, y=bb.y),
                   carla.Location(x=-bb.x, y=-bb.y)]
        corners = [x + actor.trigger_volume.location for x in corners]
        t = actor.get_transform()
        t.transform(corners)
        return corners


class World(object):
    def __init__(self,carla_world):
        self.world = carla_world
        self.vehicles_list = []
        self.walkers_list = []
        self.all_id = []
        self.all_actors = []
        self.synchronous_master = True
        self._weather_presets = find_weather_presets()
        self._weather_index = 0
        self.hero_car = None
        self.hero_transform = None
        self.camera_data = None
        self.camera_sem = None
        self.camera_rgb = None
        self.actors_with_transforms = []
        
        self.scale_offset = [0, 0]
        
        self.traffic_light_surfaces = TrafficLightSurfaces()

        self.map_image = MapImage(
        carla_world=carla_world,
        carla_map=carla_world.get_map(),
        pixels_per_meter=PIXELS_PER_METER,
        show_triggers=False,
        show_connections=False,
        show_spawn_points=False)

        self.original_surface_size = min(int(CAM_W),int(CAM_H))
        self.surface_size = self.map_image.big_map_surface.get_width()

        self.scaled_size = int(self.surface_size)
        self.prev_scaled_size = int(self.surface_size)

        # Render Actors
        self.actors_surface = pygame.Surface((self.map_image.surface.get_width(), self.map_image.surface.get_height()))
        self.actors_surface.set_colorkey(COLOR_BLACK)

        self.vehicle_id_surface = pygame.Surface((self.surface_size, self.surface_size)).convert()
        self.vehicle_id_surface.set_colorkey(COLOR_BLACK)

        self.border_round_surface = pygame.Surface((int(CAM_W),int(CAM_H)), pygame.SRCALPHA).convert()
        self.border_round_surface.set_colorkey(COLOR_WHITE)
        self.border_round_surface.fill(COLOR_BLACK)

        # Used for Hero Mode, draws the map contained in a circle with white border
        #center_offset = (int(self.hud.dim[0] / 2), int(self.hud.dim[1] / 2))
        #pygame.draw.circle(self.border_round_surface, COLOR_ALUMINIUM_1, center_offset, int(self.hud.dim[1] / 2))
        #pygame.draw.circle(self.border_round_surface, COLOR_WHITE, center_offset, int((self.hud.dim[1] - 8) / 2))

        scaled_original_size = self.original_surface_size * (1.0 / 0.9)
        self.hero_surface = pygame.Surface((scaled_original_size, scaled_original_size)).convert()

        self.result_surface = pygame.Surface((self.surface_size, self.surface_size)).convert()
        self.result_surface.set_colorkey(COLOR_BLACK)

    def _split_actors(self):
        """Splits the retrieved actors by type id"""
        vehicles = []
        traffic_lights = []
        speed_limits = []
        walkers = []

        for actor_with_transform in self.actors_with_transforms:
            actor = actor_with_transform[0]
            if 'vehicle' in actor.type_id:
                vehicles.append(actor_with_transform)
            elif 'traffic_light' in actor.type_id:
                traffic_lights.append(actor_with_transform)
            elif 'speed_limit' in actor.type_id:
                speed_limits.append(actor_with_transform)
            elif 'walker.pedestrian' in actor.type_id:
                walkers.append(actor_with_transform)

        return (vehicles, traffic_lights, speed_limits, walkers)

    def _compute_scale(self, scale_factor):
        """Based on the mouse wheel and mouse position, it will compute the scale and move the map so that it is zoomed in or out based on mouse position"""
        m = (0,0)

        # Percentage of surface where mouse position is actually
        px = (m[0] - self.scale_offset[0]) / float(self.prev_scaled_size)
        py = (m[1] - self.scale_offset[1]) / float(self.prev_scaled_size)

        # Offset will be the previously accumulated offset added with the
        # difference of mouse positions in the old and new scales
        diff_between_scales = ((float(self.prev_scaled_size) * px) - (float(self.scaled_size) * px),
                               (float(self.prev_scaled_size) * py) - (float(self.scaled_size) * py))

        self.scale_offset = (self.scale_offset[0] + diff_between_scales[0],
                             self.scale_offset[1] + diff_between_scales[1])

        # Update previous scale
        self.prev_scaled_size = self.scaled_size

        # Scale performed
        self.map_image.scale_map(scale_factor)

    # def _show_nearby_vehicles(self, vehicles):
    #     """Shows nearby vehicles of the hero actor"""
    #     info_text = []
    #     if self.player is not None and len(vehicles) > 1:
    #         location = self.hero_transform.location
    #         vehicle_list = [x[0] for x in vehicles if x[0].id != self.player.id]

    #         def distance(v): return location.distance(v.get_location())
    #         for n, vehicle in enumerate(sorted(vehicle_list, key=distance)):
    #             if n > 15:
    #                 break
    #             vehicle_type = ''
    #             info_text.append('% 5d %s' % (vehicle.id, vehicle_type))
        #self.hud.add_info('NEARBY VEHICLES', info_text)
    def clip_surfaces(self, clipping_rect):
        """Used to improve perfomance. Clips the surfaces in order to render only the part of the surfaces that are going to be visible"""
        self.actors_surface.set_clip(clipping_rect)
        self.vehicle_id_surface.set_clip(clipping_rect)
        self.result_surface.set_clip(clipping_rect)


    def _render_traffic_lights(self, surface, list_tl, world_to_pixel):
        """Renders the traffic lights and shows its triggers and bounding boxes if flags are enabled"""
        self.affected_traffic_light = None

        for tl in list_tl:
            world_pos = tl.get_location()
            pos = world_to_pixel(world_pos)

            if self.args.show_triggers:
                corners = Util.get_bounding_box(tl)
                corners = [world_to_pixel(p) for p in corners]
                pygame.draw.lines(surface, COLOR_BUTTER_1, True, corners, 2)

            if self.player is not None:
                corners = Util.get_bounding_box(tl)
                corners = [world_to_pixel(p) for p in corners]
                tl_t = tl.get_transform()

                transformed_tv = tl_t.transform(tl.trigger_volume.location)
                hero_location = self.player.get_location()
                d = hero_location.distance(transformed_tv)
                s = Util.length(tl.trigger_volume.extent) + Util.length(self.player.bounding_box.extent)
                if (d <= s):
                    # Highlight traffic light
                    self.affected_traffic_light = tl
                    srf = self.traffic_light_surfaces.surfaces['h']
                    surface.blit(srf, srf.get_rect(center=pos))

            srf = self.traffic_light_surfaces.surfaces[tl.state]
            surface.blit(srf, srf.get_rect(center=pos))

    def _render_speed_limits(self, surface, list_sl, world_to_pixel, world_to_pixel_width):
        """Renders the speed limits by drawing two concentric circles (outer is red and inner white) and a speed limit text"""

        font_size = world_to_pixel_width(2)
        radius = world_to_pixel_width(2)
        font = pygame.font.SysFont('Arial', font_size)

        for sl in list_sl:

            x, y = world_to_pixel(sl.get_location())

            # Render speed limit concentric circles
            white_circle_radius = int(radius * 0.75)

            pygame.draw.circle(surface, COLOR_SCARLET_RED_1, (x, y), radius)
            pygame.draw.circle(surface, COLOR_ALUMINIUM_0, (x, y), white_circle_radius)

            limit = sl.type_id.split('.')[2]
            font_surface = font.render(limit, True, COLOR_ALUMINIUM_5)

            if self.args.show_triggers:
                corners = Util.get_bounding_box(sl)
                corners = [world_to_pixel(p) for p in corners]
                pygame.draw.lines(surface, COLOR_PLUM_2, True, corners, 2)

            # Blit
            if self.hero_car is not None:
                # In hero mode, Rotate font surface with respect to hero vehicle front
                angle = -self.hero_transform.rotation.yaw - 90.0
                font_surface = pygame.transform.rotate(font_surface, angle)
                offset = font_surface.get_rect(center=(x, y))
                surface.blit(font_surface, offset)

            else:
                # In map mode, there is no need to rotate the text of the speed limit
                surface.blit(font_surface, (x - radius / 2, y - radius / 2))

    def _render_walkers(self, surface, list_w, world_to_pixel):
        """Renders the walkers' bounding boxes"""
        for w in list_w:
            color = COLOR_PLUM_0

            # Compute bounding box points
            bb = w[0].bounding_box.extent
            corners = [
                carla.Location(x=-bb.x, y=-bb.y),
                carla.Location(x=bb.x, y=-bb.y),
                carla.Location(x=bb.x, y=bb.y),
                carla.Location(x=-bb.x, y=bb.y)]

            w[1].transform(corners)
            corners = [world_to_pixel(p) for p in corners]
            pygame.draw.polygon(surface, color, corners)

    def _render_vehicles(self, surface, list_v, world_to_pixel):
        """Renders the vehicles' bounding boxes"""
        for v in list_v:
            color = COLOR_SKY_BLUE_0
            if int(v[0].attributes['number_of_wheels']) == 2:
                color = COLOR_CHOCOLATE_1
            if v[0].attributes['role_name'] == 'hero':
                color = COLOR_CHAMELEON_0
            # Compute bounding box points
            bb = v[0].bounding_box.extent
            corners = [carla.Location(x=-bb.x, y=-bb.y),
                       carla.Location(x=bb.x - 0.8, y=-bb.y),
                       carla.Location(x=bb.x, y=0),
                       carla.Location(x=bb.x - 0.8, y=bb.y),
                       carla.Location(x=-bb.x, y=bb.y),
                       carla.Location(x=-bb.x, y=-bb.y)
                       ]
            v[1].transform(corners)
            corners = [world_to_pixel(p) for p in corners]
            pygame.draw.lines(surface, color, False, corners, int(math.ceil(4.0 * self.map_image.scale)))



    def render_actors(self, surface, vehicles, traffic_lights, speed_limits, walkers):
        """Renders all the actors"""
        # Static actors
        self._render_traffic_lights(surface, [tl[0] for tl in traffic_lights], self.map_image.world_to_pixel)
        self._render_speed_limits(surface, [sl[0] for sl in speed_limits], self.map_image.world_to_pixel,
                                  self.map_image.world_to_pixel_width)

        # Dynamic actors
        self._render_vehicles(surface, vehicles, self.map_image.world_to_pixel)
        self._render_walkers(surface, walkers, self.map_image.world_to_pixel)

    def map_render(self):
        """Renders the map and all the actors in hero and map mode"""
        if self.actors_with_transforms is None:
            return
        self.result_surface.fill(COLOR_BLACK)

        # Split the actors by vehicle type id
        vehicles, traffic_lights, speed_limits, walkers = self._split_actors()

        # Zoom in and out
        scale_factor = 1 #hard coded - originallly input from mouse wheel was used
        self.scaled_size = int(self.map_image.width * scale_factor)
        if self.scaled_size != self.prev_scaled_size:
            self._compute_scale(scale_factor)

        # Render Actors
        self.actors_surface.fill(COLOR_BLACK)
        self.render_actors(
            self.actors_surface,
            vehicles,
            traffic_lights,
            speed_limits,
            walkers)

        # Render Ids
        # self.hud.render_vehicles_ids(self.vehicle_id_surface, vehicles,
        #                               self.map_image.world_to_pixel, self.player, self.hero_transform)
        # Show nearby actors from hero mode
        #self._show_nearby_vehicles(vehicles)

        # Blit surfaces
        surfaces = ((self.map_image.surface, (0, 0)),
                    (self.actors_surface, (0, 0)),
                    (self.vehicle_id_surface, (0, 0)),
                    )

        angle = 0.0 if self.hero_car is None else self.hero_transform.rotation.yaw + 90.0
        self.traffic_light_surfaces.rotozoom(-angle, self.map_image.scale)

        # Hero Mode Only in this use
        hero_location_screen = self.map_image.world_to_pixel(self.hero_transform.location)
        hero_front = self.hero_transform.get_forward_vector()
        
        translation_offset = (hero_location_screen[0] - self.hero_surface.get_width() / 2 + hero_front.x * PIXELS_AHEAD_VEHICLE,
                                (hero_location_screen[1] - self.hero_surface.get_height() / 2 + hero_front.y * PIXELS_AHEAD_VEHICLE))

        # Apply clipping rect
        clipping_rect = pygame.Rect(translation_offset[0],
                                    translation_offset[1],
                                    self.hero_surface.get_width(),
                                    self.hero_surface.get_height())
        self.clip_surfaces(clipping_rect)

        Util.blits(self.result_surface, surfaces)

        self.border_round_surface.set_clip(clipping_rect)

        self.hero_surface.fill(COLOR_ALUMINIUM_4)
        self.hero_surface.blit(self.result_surface, (-translation_offset[0],
                                                        -translation_offset[1]))
        rotated_result_surface = pygame.transform.rotozoom(self.hero_surface, angle, 0.9).convert()

        _width = rotated_result_surface.get_width()
        _height = rotated_result_surface.get_height()
        _new_width = math.floor(_width / MAP_CAPTURE_CROP_FACTOR)
        _new_height = math.floor(_height / MAP_CAPTURE_CROP_FACTOR)
        _new_width_start = math.floor(_width / 2) - math.floor(_new_width / 2)
        _new_height_start = math.floor(_height / 2) - math.floor(_new_height / 2)
        slice_rect = pygame.Rect(_new_width_start, _new_height_start, _new_width, _new_height)
        return rotated_result_surface.subsurface(slice_rect)
        
    def attach_sensors(self):
            '''
            attaches 2 cameras to hero car

            '''

            #semantic camera
            camera_bp = self.world.get_blueprint_library().find('sensor.camera.semantic_segmentation')
            camera_bp.set_attribute('image_size_x', CAM_W) # this ratio works in CARLA 9.13 on Windows
            camera_bp.set_attribute('image_size_y', CAM_H)
            camera_bp.set_attribute('fov', '90')

            camera_init_trans = carla.Transform(carla.Location(z=CAMERA_POS_Z,x=CAMERA_POS_X))
            self.camera_sem = self.world.spawn_actor(camera_bp,camera_init_trans,attach_to=self.hero_car)

            #normal rgb camera
            camera_bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
            camera_bp.set_attribute('image_size_x', CAM_W) # this ratio works in CARLA 9.13 on Windows
            camera_bp.set_attribute('image_size_y', CAM_H)
            camera_bp.set_attribute('fov', '90')
            camera_init_trans = carla.Transform(carla.Location(z=CAMERA_POS_Z,x=CAMERA_POS_X))
            self.camera_rgb = self.world.spawn_actor(camera_bp,camera_init_trans,attach_to=self.hero_car)
            image_w = int(CAM_W)
            image_h = int(CAM_H)
            self.camera_data = {'sem_image': np.zeros((image_h,image_w,4)),
                        'rgb_image': np.zeros((image_h,image_w,4))}
            # this actually opens a live stream from the cameras
            self.camera_sem.listen(lambda image: sem_callback(image,self.camera_data))
            self.camera_rgb.listen(lambda image: rgb_callback(image,self.camera_data))

    def destroy_traffic(self,client):
        '''
        destroy all previous traffic
        '''
        print('\ndestroying %d vehicles' % len(self.vehicles_list))
        client.apply_batch([carla.command.DestroyActor(x) for x in self.vehicles_list])

        # stop walker controllers (list is [controller, actor, controller, actor ...])
        for i in range(0, len(self.all_id), 2):
            self.all_actors[i].stop()

        print('\ndestroying %d walkers' % len(self.walkers_list))
        client.apply_batch([carla.command.DestroyActor(x) for x in self.all_id])
        self.vehicles_list = []
        self.walkers_list = []
        self.all_id = []
        self.all_actors = []
    
    def generate_traffic(self,client,number_of_vehicles,number_of_walkers):
        traffic_manager = client.get_trafficmanager(8000)
        traffic_manager.set_global_distance_to_leading_vehicle(2.5)
        
        traffic_manager.set_hybrid_physics_mode(True)
        traffic_manager.set_hybrid_physics_radius(70.0)


        settings = self.world.get_settings()
        self.synchronous_master = True
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.05
        settings.no_rendering_mode = NO_RENDERING
        self.world.apply_settings(settings)
        
        print('commencing spawning actors...')

        blueprints = get_actor_blueprints(self.world, 'vehicle.*', 'All')
        if not blueprints:
            raise ValueError("Couldn't find any vehicles with the specified filters")
        blueprintsWalkers = get_actor_blueprints(self.world, 'walker.pedestrian.*','2')
        if not blueprintsWalkers:
            raise ValueError("Couldn't find any walkers with the specified filters")

        blueprints = [x for x in blueprints if x.get_attribute('base_type') == 'car']

        blueprints = sorted(blueprints, key=lambda bp: bp.id)

        spawn_points = self.world.get_map().get_spawn_points()
        number_of_spawn_points = len(spawn_points)

        if number_of_vehicles < number_of_spawn_points:
            random.shuffle(spawn_points)
        elif number_of_vehicles > number_of_spawn_points:
            msg = 'requested %d vehicles, but could only find %d spawn points'
            logging.warning(msg, number_of_vehicles, number_of_spawn_points)
            number_of_vehicles = number_of_spawn_points

        # @todo cannot import these directly.
        SpawnActor = carla.command.SpawnActor
        SetAutopilot = carla.command.SetAutopilot
        FutureActor = carla.command.FutureActor
        print('commencing spawning vehicles...')

        # --------------
        # Spawn vehicles
        # --------------
        batch = []
        for n, transform in enumerate(spawn_points):
            if n >= number_of_vehicles:
                break
            if n==0:
                blueprint = random.choice(self.world.get_blueprint_library().filter("vehicle.tesla.model3"))
            else:
                blueprint = random.choice(blueprints)
            if blueprint.has_attribute('color'):
                color = random.choice(blueprint.get_attribute('color').recommended_values)
                blueprint.set_attribute('color', color)
            if blueprint.has_attribute('driver_id'):
                driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
                blueprint.set_attribute('driver_id', driver_id)
            blueprint.set_attribute('role_name', 'autopilot')

            # spawn the cars and set their autopilot and light state all together
            batch.append(SpawnActor(blueprint, transform)
                .then(SetAutopilot(FutureActor, True, traffic_manager.get_port())))

        for response in client.apply_batch_sync(batch, self.synchronous_master):
            if response.error:
                logging.error(response.error)
            else:
                self.vehicles_list.append(response.actor_id)

        # Set automatic vehicle lights update if specified
    
        all_vehicle_actors = self.world.get_actors(self.vehicles_list)
        for actor in all_vehicle_actors:
            traffic_manager.update_vehicle_lights(actor, True)
    
        print('commencing spawning walkers...')

        # -------------
        # Spawn Walkers
        # -------------
        # some settings
        percentagePedestriansRunning = 0.0      # how many pedestrians will run
        percentagePedestriansCrossing = 0.0     # how many pedestrians will walk through the road
        # 1. take all the random locations to spawn
        spawn_points = []
        for i in range(number_of_walkers):
            spawn_point = carla.Transform()
            loc = self.world.get_random_location_from_navigation()
            if (loc != None):
                spawn_point.location = loc
                spawn_points.append(spawn_point)
        # 2. we spawn the walker object
        batch = []
        walker_speed = []
        for spawn_point in spawn_points:
            walker_bp = random.choice(blueprintsWalkers)
            # set as not invincible
            if walker_bp.has_attribute('is_invincible'):
                walker_bp.set_attribute('is_invincible', 'false')
            # set the max speed
            if walker_bp.has_attribute('speed'):
                if (random.random() > percentagePedestriansRunning):
                    # walking
                    walker_speed.append(walker_bp.get_attribute('speed').recommended_values[1])
                else:
                    # running
                    walker_speed.append(walker_bp.get_attribute('speed').recommended_values[2])
            else:
                print("Walker has no speed")
                walker_speed.append(0.0)
            batch.append(SpawnActor(walker_bp, spawn_point))
        results = client.apply_batch_sync(batch, True)
        walker_speed2 = []
        for i in range(len(results)):
            if results[i].error:
                logging.error(results[i].error)
            else:
                self.walkers_list.append({"id": results[i].actor_id})
                walker_speed2.append(walker_speed[i])
        walker_speed = walker_speed2
        # 3. we spawn the walker controller
        batch = []
        walker_controller_bp = self.world.get_blueprint_library().find('controller.ai.walker')
        for i in range(len(self.walkers_list)):
            batch.append(SpawnActor(walker_controller_bp, carla.Transform(), self.walkers_list[i]["id"]))
        results = client.apply_batch_sync(batch, True)
        for i in range(len(results)):
            if results[i].error:
                logging.error(results[i].error)
            else:
                self.walkers_list[i]["con"] = results[i].actor_id
        # 4. we put together the walkers and controllers id to get the objects from their id
        for i in range(len(self.walkers_list)):
            self.all_id.append(self.walkers_list[i]["con"])
            self.all_id.append(self.walkers_list[i]["id"])
        self.all_actors = self.world.get_actors(self.all_id)
        
        # wait for a tick to ensure client receives the last transform of the walkers we have just created
        self.world.tick()

        # 5. initialize each controller and set target to walk to (list is [controler, actor, controller, actor ...])
        # set how many pedestrians can cross the road
        self.world.set_pedestrians_cross_factor(percentagePedestriansCrossing)
        for i in range(0, len(self.all_id), 2):
            # start walker
            self.all_actors[i].start()
            # set walk to random point
            self.all_actors[i].go_to_location(self.world.get_random_location_from_navigation())
            # max speed
            self.all_actors[i].set_max_speed(float(walker_speed[int(i/2)]))

        print('spawned %d vehicles and %d walkers, press Ctrl+Q to exit.' % (len(self.vehicles_list), len(self.walkers_list)))

        # Example of how to use Traffic Manager parameters
        traffic_manager.global_percentage_speed_difference(30.0)
        self.hero_car = self.world.get_actors(world.vehicles_list)[0]
    
    def next_weather(self, reverse=False):
        self._weather_index += -1 if reverse else 1
        self._weather_index %= len(self._weather_presets)
        preset = self._weather_presets[self._weather_index]
        self.world.set_weather(preset[0])
#main code

client = carla.Client("localhost", 2000)
client.set_timeout(10.0)
pygame.init()
pygame.display.set_mode((1, 1))
quit_status = False
for town in MAPS:
        print('Loading town:',town)
        client.load_world(town)
        sim_world = client.get_world()
        original_settings = sim_world.get_settings()

        world = World(sim_world)

        spectator = sim_world.get_spectator()
        world.generate_traffic(client,number_of_vehicles=20,number_of_walkers=30)
        world.attach_sensors()
        
        #tick loop
        duration = 1_000
        for i in range(duration):
            sim_world.tick()
            time_grab = time.time_ns()
            #actors = sim_world.get_actors() # can use 
            world.actors_with_transforms = [(actor, actor.get_transform()) for actor in world.all_actors]
            world.hero_transform = world.hero_car.get_transform()
            # optional - move spectator behind a car
            # adjust_spectator() 
            rgb_im = world.camera_data['rgb_image']
            sem_im = world.camera_data['sem_image']
            map = world.map_render() # render the map
            pygame.image.save(map, MAP_FOLDER+'%06d.png' % time_grab)
            #im_h = cv2.hconcat([rgb_im,sem_im])
            cv2.imshow('semantic', sem_im)
            if cv2.waitKey(1) == ord('q'):
                quit_status = True
                break
            if i % 500 ==0:
                print('Have gone through ',i,' out of ',duration,' cycles')
                world.next_weather(reverse=False)

        world.destroy_traffic(client)
        sim_world.tick()
        sim_world.apply_settings(original_settings)
        if quit_status:
            break