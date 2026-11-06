"""Shared mapping from film time to physical simulation time."""

FPS=24
DESIGN_SOURCE_FRAMES=384
DESIGN_FRAMES=576
LAUNCH_FRAMES=336


def design_source_frame(output_frame):
    chapter=min((output_frame-1)//144,3)
    within=(output_frame-1)%144
    return chapter*96+min(within,95)+1


def physical_time(film_t,apogee_time):
    if film_t<1.5:return 0.0,0.0
    if film_t<5.5:return (film_t-1.5)*.2,.2
    if film_t<11.5:return .8+(film_t-5.5)*(apogee_time-.8)/6,(apogee_time-.8)/6
    return apogee_time,0.0
