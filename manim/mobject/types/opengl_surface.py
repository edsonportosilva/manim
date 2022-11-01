import moderngl
import numpy as np

from ...constants import *
from ...mobject.opengl_mobject import OpenGLMobject
from ...utils.bezier import integer_interpolate, interpolate
from ...utils.color import *
from ...utils.config_ops import _Data, _Uniforms
from ...utils.images import get_full_raster_image_path
from ...utils.iterables import listify
from ...utils.space_ops import normalize_along_axis


class OpenGLSurface(OpenGLMobject):
    shader_dtype = [
        ("point", np.float32, (3,)),
        ("du_point", np.float32, (3,)),
        ("dv_point", np.float32, (3,)),
        ("color", np.float32, (4,)),
    ]
    shader_folder = "surface"

    def __init__(
        self,
        uv_func=None,
        u_range=None,
        v_range=None,
        # Resolution counts number of points sampled, which for
        # each coordinate is one more than the the number of
        # rows/columns of approximating squares
        resolution=None,
        color=GREY,
        opacity=1.0,
        gloss=0.3,
        shadow=0.4,
        prefered_creation_axis=1,
        # For du and dv steps.  Much smaller and numerical error
        # can crop up in the shaders.
        epsilon=1e-5,
        render_primitive=moderngl.TRIANGLES,
        depth_test=True,
        shader_folder=None,
        **kwargs
    ):
        self.passed_uv_func = uv_func
        self.u_range = u_range if u_range is not None else (0, 1)
        self.v_range = v_range if v_range is not None else (0, 1)
        # Resolution counts number of points sampled, which for
        # each coordinate is one more than the the number of
        # rows/columns of approximating squares
        self.resolution = resolution if resolution is not None else (101, 101)
        self.prefered_creation_axis = prefered_creation_axis
        # For du and dv steps.  Much smaller and numerical error
        # can crop up in the shaders.
        self.epsilon = epsilon

        super().__init__(
            color=color,
            opacity=opacity,
            gloss=gloss,
            shadow=shadow,
            shader_folder=shader_folder if shader_folder is not None else "surface",
            render_primitive=render_primitive,
            depth_test=depth_test,
            **kwargs
        )
        self.compute_triangle_indices()

    def uv_func(self, u, v):
        # To be implemented in subclasses
        return self.passed_uv_func(u, v) if self.passed_uv_func else (u, v, 0.0)

    def init_points(self):
        dim = self.dim
        nu, nv = self.resolution
        u_range = np.linspace(*self.u_range, nu)
        v_range = np.linspace(*self.v_range, nv)

        # Get three lists:
        # - Points generated by pure uv values
        # - Those generated by values nudged by du
        # - Those generated by values nudged by dv
        point_lists = []
        for (du, dv) in [(0, 0), (self.epsilon, 0), (0, self.epsilon)]:
            uv_grid = np.array([[[u + du, v + dv] for v in v_range] for u in u_range])
            point_grid = np.apply_along_axis(lambda p: self.uv_func(*p), 2, uv_grid)
            point_lists.append(point_grid.reshape((nu * nv, dim)))
        # Rather than tracking normal vectors, the points list will hold on to the
        # infinitesimal nudged values alongside the original values.  This way, one
        # can perform all the manipulations they'd like to the surface, and normals
        # are still easily recoverable.
        self.set_points(np.vstack(point_lists))

    def compute_triangle_indices(self):
        # TODO, if there is an event which changes
        # the resolution of the surface, make sure
        # this is called.
        nu, nv = self.resolution
        if nu == 0 or nv == 0:
            self.triangle_indices = np.zeros(0, dtype=int)
            return
        index_grid = np.arange(nu * nv).reshape((nu, nv))
        indices = np.zeros(6 * (nu - 1) * (nv - 1), dtype=int)
        indices[::6] = index_grid[:-1, :-1].flatten()
        indices[1::6] = index_grid[+1:, :-1].flatten()  # Bottom left
        indices[2::6] = index_grid[:-1, +1:].flatten()  # Top right
        indices[3::6] = index_grid[:-1, +1:].flatten()  # Top right
        indices[4::6] = index_grid[+1:, :-1].flatten()  # Bottom left
        indices[5::6] = index_grid[+1:, +1:].flatten()  # Bottom right
        self.triangle_indices = indices

    def get_triangle_indices(self):
        return self.triangle_indices

    def get_surface_points_and_nudged_points(self):
        points = self.points
        k = len(points) // 3
        return points[:k], points[k : 2 * k], points[2 * k :]

    def get_unit_normals(self):
        s_points, du_points, dv_points = self.get_surface_points_and_nudged_points()
        normals = np.cross(
            (du_points - s_points) / self.epsilon,
            (dv_points - s_points) / self.epsilon,
        )
        return normalize_along_axis(normals, 1)

    def pointwise_become_partial(self, smobject, a, b, axis=None):
        assert isinstance(smobject, OpenGLSurface)
        if axis is None:
            axis = self.prefered_creation_axis
        if a <= 0 and b >= 1:
            self.match_points(smobject)
            return self

        nu, nv = smobject.resolution
        self.set_points(
            np.vstack(
                [
                    self.get_partial_points_array(
                        arr.copy(),
                        a,
                        b,
                        (nu, nv, 3),
                        axis=axis,
                    )
                    for arr in smobject.get_surface_points_and_nudged_points()
                ],
            ),
        )
        return self

    def get_partial_points_array(self, points, a, b, resolution, axis):
        if len(points) == 0:
            return points
        nu, nv = resolution[:2]
        points = points.reshape(resolution)
        max_index = resolution[axis] - 1
        lower_index, lower_residue = integer_interpolate(0, max_index, a)
        upper_index, upper_residue = integer_interpolate(0, max_index, b)
        if axis == 0:
            points[:lower_index] = interpolate(
                points[lower_index],
                points[lower_index + 1],
                lower_residue,
            )
            points[upper_index + 1 :] = interpolate(
                points[upper_index],
                points[upper_index + 1],
                upper_residue,
            )
        else:
            shape = (nu, 1, resolution[2])
            points[:, :lower_index] = interpolate(
                points[:, lower_index],
                points[:, lower_index + 1],
                lower_residue,
            ).reshape(shape)
            points[:, upper_index + 1 :] = interpolate(
                points[:, upper_index],
                points[:, upper_index + 1],
                upper_residue,
            ).reshape(shape)
        return points.reshape((nu * nv, *resolution[2:]))

    def sort_faces_back_to_front(self, vect=OUT):
        tri_is = self.triangle_indices
        indices = list(range(len(tri_is) // 3))
        points = self.points

        def index_dot(index):
            return np.dot(points[tri_is[3 * index]], vect)

        indices.sort(key=index_dot)
        for k in range(3):
            tri_is[k::3] = tri_is[k::3][indices]
        return self

    # For shaders
    def get_shader_data(self):
        s_points, du_points, dv_points = self.get_surface_points_and_nudged_points()
        shader_data = np.zeros(len(s_points), dtype=self.shader_dtype)
        if "points" not in self.locked_data_keys:
            shader_data["point"] = s_points
            shader_data["du_point"] = du_points
            shader_data["dv_point"] = dv_points
        self.fill_in_shader_color_info(shader_data)
        return shader_data

    def fill_in_shader_color_info(self, shader_data):
        self.read_data_to_shader(shader_data, "color", "rgbas")
        return shader_data

    def get_shader_vert_indices(self):
        return self.get_triangle_indices()

    def set_fill_by_value(self, axes, colors):
        # directly copied from three_dimensions.py with some compatibility changes.
        """Sets the color of each mobject of a parametric surface to a color relative to its z-value

        Parameters
        ----------
        axes :
            The axes for the parametric surface, which will be used to map z-values to colors.
        colors :
            A list of colors, ordered from lower z-values to higher z-values. If a list of tuples is passed
            containing colors paired with numbers, then those numbers will be used as the pivots.

        Returns
        -------
        :class:`~.Surface`
            The parametric surface with a gradient applied by value. For chaining.

        Examples
        --------
        .. manim:: FillByValueExample
            :save_last_frame:

            class FillByValueExample(ThreeDScene):
                def construct(self):
                    resolution_fa = 42
                    self.set_camera_orientation(phi=75 * DEGREES, theta=-120 * DEGREES)
                    axes = ThreeDAxes(x_range=(0, 5, 1), y_range=(0, 5, 1), z_range=(-1, 1, 0.5))
                    def param_surface(u, v):
                        x = u
                        y = v
                        z = np.sin(x) * np.cos(y)
                        return z
                    surface_plane = Surface(
                        lambda u, v: axes.c2p(u, v, param_surface(u, v)),
                        resolution=(resolution_fa, resolution_fa),
                        v_range=[0, 5],
                        u_range=[0, 5],
                        )
                    # surface_plane.set_style(fill_opacity=1)
                    surface_plane.set_fill_by_value(axes=axes, colors=[(RED, -0.4), (YELLOW, 0), (GREEN, 0.4)])
                    self.add(axes, surface_plane)
        """
        if type(colors[0]) is tuple:
            new_colors, pivots = [[i for i, j in colors], [j for i, j in colors]]
        else:
            new_colors = colors

            pivot_min = axes.z_range[0]
            pivot_max = axes.z_range[1]
            pivot_frequency = (pivot_max - pivot_min) / (len(new_colors) - 1)
            pivots = np.arange(
                start=pivot_min,
                stop=pivot_max + pivot_frequency,
                step=pivot_frequency,
            )

        for mob in self.family_members_with_points():
            # import ipdb; ipdb.set_trace(context=7)
            z_value = axes.point_to_coords(mob.get_midpoint())[2]
            if z_value <= pivots[0]:
                mob.set_color(new_colors[0])
            elif z_value >= pivots[-1]:
                mob.set_color(new_colors[-1])
            else:
                for i, pivot in enumerate(pivots):
                    if pivot > z_value:
                        color_index = (z_value - pivots[i - 1]) / (
                            pivots[i] - pivots[i - 1]
                        )
                        color_index = min(color_index, 1)
                        mob_color = interpolate_color(
                            new_colors[i - 1],
                            new_colors[i],
                            color_index,
                        )
                        mob.set_color(mob_color, recurse=False)

                        break

        return self


class OpenGLSurfaceGroup(OpenGLSurface):
    def __init__(self, *parametric_surfaces, resolution=None, **kwargs):
        self.resolution = (0, 0) if resolution is None else resolution
        super().__init__(uv_func=None, **kwargs)
        self.add(*parametric_surfaces)

    def init_points(self):
        pass  # Needed?


class OpenGLTexturedSurface(OpenGLSurface):
    shader_dtype = [
        ("point", np.float32, (3,)),
        ("du_point", np.float32, (3,)),
        ("dv_point", np.float32, (3,)),
        ("im_coords", np.float32, (2,)),
        ("opacity", np.float32, (1,)),
    ]
    shader_folder = "textured_surface"
    im_coords = _Data()
    opacity = _Data()
    num_textures = _Uniforms()

    def __init__(
        self, uv_surface, image_file, dark_image_file=None, shader_folder=None, **kwargs
    ):
        self.uniforms = {}

        if not isinstance(uv_surface, OpenGLSurface):
            raise Exception("uv_surface must be of type OpenGLSurface")
        # Set texture information
        if dark_image_file is None:
            dark_image_file = image_file
            self.num_textures = 1
        else:
            self.num_textures = 2
        texture_paths = {
            "LightTexture": get_full_raster_image_path(image_file),
            "DarkTexture": get_full_raster_image_path(dark_image_file),
        }

        self.uv_surface = uv_surface
        self.uv_func = uv_surface.uv_func
        self.u_range = uv_surface.u_range
        self.v_range = uv_surface.v_range
        self.resolution = uv_surface.resolution
        self.gloss = self.uv_surface.gloss
        super().__init__(texture_paths=texture_paths, **kwargs)

    def init_data(self):
        super().init_data()
        self.im_coords = np.zeros((0, 2))
        self.opacity = np.zeros((0, 1))

    def init_points(self):
        nu, nv = self.uv_surface.resolution
        self.set_points(self.uv_surface.points)
        self.im_coords = np.array(
            [
                [u, v]
                for u in np.linspace(0, 1, nu)
                for v in np.linspace(1, 0, nv)  # Reverse y-direction
            ],
        )

    def init_colors(self):
        self.opacity = np.array([self.uv_surface.rgbas[:, 3]])

    def set_opacity(self, opacity, recurse=True):
        for mob in self.get_family(recurse):
            mob.opacity = np.array([[o] for o in listify(opacity)])
        return self

    def pointwise_become_partial(self, tsmobject, a, b, axis=1):
        super().pointwise_become_partial(tsmobject, a, b, axis)
        im_coords = self.im_coords
        im_coords[:] = tsmobject.im_coords
        if a <= 0 and b >= 1:
            return self
        nu, nv = tsmobject.resolution
        im_coords[:] = self.get_partial_points_array(im_coords, a, b, (nu, nv, 2), axis)
        return self

    def fill_in_shader_color_info(self, shader_data):
        self.read_data_to_shader(shader_data, "opacity", "opacity")
        self.read_data_to_shader(shader_data, "im_coords", "im_coords")
        return shader_data
