from gym.envs.registration import register

register(
    id='multigoal-v0',
    entry_point='gym_multigoal.envs:MultiGoalEnv',
)
