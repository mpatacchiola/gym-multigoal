import numpy as np
import matplotlib.pyplot as plt

#from garage.core.serializable import Serializable
#from gym.spaces import Box
#from garage.misc import logger

import gym
from gym import error, spaces, utils
from gym.utils import seeding

class MultiGoalEnv(gym.Env):
    """
    Move a 2D point mass to one of the goal positions. Cost is the distance to
    the closest goal.

    State: position.
    Action: velocity.
    """

    def __init__(self, 
                 goal_reward=10, 
                 actuation_cost_coeff=30,
                 distance_cost_coeff=1, 
                 init_sigma=0.1, 
                 step_limit=500):
        super(MultiGoalEnv, self).__init__()

        self.step_limit = step_limit        
        self.dynamics = PointDynamics(dim=2, sigma=0)
        self.init_mu = np.zeros(2, dtype=np.float32)
        self.init_sigma = init_sigma
        self.goal_positions = np.array(
            [
                [5, 0],
                [-5, 0],
                [0, 5],
                [0, -5]
            ],
            dtype=np.float32
        )
        self.goal_threshold = 1.
        self.goal_reward = goal_reward
        self.action_cost_coeff = actuation_cost_coeff
        self.distance_cost_coeff = distance_cost_coeff
        self.xlim = (-7, 7)
        self.ylim = (-7, 7)
        self.vel_bound = 1.
        self.reset()
        self.observation = None

        self.reward_range = (-float('inf'), float('inf'))
        self.metadata = {'render.modes': []}
        self.spec = None

        self._ax = None
        self._env_lines = []
        self.fixed_plots = None
        self.dynamic_plots = []
        
        self.position_list = list()


    def reset(self):
        unclipped_observation = self.init_mu + self.init_sigma * \
                                np.random.normal(size=self.dynamics.s_dim)
        o_lb, o_ub = self.observation_space.low, self.observation_space.high
        self.observation = np.clip(unclipped_observation, o_lb, o_ub)
        self.step_counter=0
        self.position_list = list() # clear the position list
        self.position_list.append(self.observation)
        return self.observation

    @property
    def observation_space(self):
        return spaces.Box(
            low=np.array((self.xlim[0], self.ylim[0]), dtype=np.float32),
            high=np.array((self.xlim[1], self.ylim[1]), dtype=np.float32),
            shape=None,
            dtype=np.float32
        )

    @property
    def action_space(self):
        return spaces.Box(
            low=-self.vel_bound,
            high=self.vel_bound,
            shape=(self.dynamics.a_dim,),
            dtype=np.float32
        )

    def get_current_obs(self):
        return np.copy(self.observation)

    def step(self, action):
        action = action.ravel()

        a_lb, a_ub = self.action_space.low, self.action_space.high
        action = np.clip(action, a_lb, a_ub).ravel()

        next_obs = self.dynamics.forward(self.observation, action)
        o_lb, o_ub = self.observation_space.low, self.observation_space.high
        next_obs = np.clip(next_obs, o_lb, o_ub)

        self.observation = np.copy(next_obs)
        self.position_list.append(self.observation) #append to the list

        reward = self.compute_reward(self.observation, action)
        cur_position = self.observation
        dist_to_goal = np.amin([
            np.linalg.norm(cur_position - goal_position)
            for goal_position in self.goal_positions
        ])
        done = dist_to_goal < self.goal_threshold
        if done:
            reward += self.goal_reward

        # Step counter update
        self.step_counter+=1
        if(self.step_counter>=self.step_limit):
            self.step_counter=0
            done = True
            
        return next_obs, reward, done, {'pos': next_obs}

    def _init_plot(self):
        fig_env = plt.figure(figsize=(7, 7))
        self._ax = fig_env.add_subplot(111)
        self._ax.axis('equal')

        self._env_lines = []
        self._ax.set_xlim((-7, 7))
        self._ax.set_ylim((-7, 7))

        self._ax.set_title('Multigoal Environment')
        self._ax.set_xlabel('x')
        self._ax.set_ylabel('y')

        self._plot_position_cost(self._ax)

    def _render(self, paths):
        if self._ax is None:
            self._init_plot()
        # noinspection PyArgumentList
        [line.remove() for line in self._env_lines]
        self._env_lines = []        
        for path in paths:
            positions = np.stack([info['pos'] for info in path['env_infos']])
            xx = positions[:, 0]
            yy = positions[:, 1]
            self._env_lines += self._ax.plot(xx, yy, 'b')
        plt.draw()
        plt.pause(0.01)


    def render(self, mode='png', file_path='./multigoal.png'):
        if self._ax is None:
            self._init_plot()

        # noinspection PyArgumentList
        [line.remove() for line in self._env_lines]
        self._env_lines = []
        
        positions = np.array(self.position_list)
        xx = positions[:, 0]
        yy = positions[:, 1]
        self._env_lines += self._ax.plot(xx, yy, 'b')
        
        plt.savefig(file_path, dpi=150)


    def compute_reward(self, observation, action):
        # penalize the L2 norm of acceleration
        # noinspection PyTypeChecker
        action_cost = np.sum(action ** 2) * self.action_cost_coeff

        # penalize squared dist to goal
        cur_position = observation
        # noinspection PyTypeChecker
        goal_cost = self.distance_cost_coeff * np.amin([
            np.sum((cur_position - goal_position) ** 2)
            for goal_position in self.goal_positions
        ])

        # penalize staying with the log barriers
        costs = [action_cost, goal_cost]
        reward = -np.sum(costs)
        return reward

    def _plot_position_cost(self, ax):
        delta = 0.01
        x_min, x_max = tuple(1.1 * np.array(self.xlim))
        y_min, y_max = tuple(1.1 * np.array(self.ylim))
        X, Y = np.meshgrid(
            np.arange(x_min, x_max, delta),
            np.arange(y_min, y_max, delta)
        )
        goal_costs = np.amin([
            (X - goal_x) ** 2 + (Y - goal_y) ** 2
            for goal_x, goal_y in self.goal_positions
        ], axis=0)
        costs = goal_costs

        contours = ax.contour(X, Y, costs, 20)
        ax.clabel(contours, inline=1, fontsize=10, fmt='%.0f')
        ax.set_xlim([x_min, x_max])
        ax.set_ylim([y_min, y_max])
        goal = ax.plot(self.goal_positions[:, 0],
                       self.goal_positions[:, 1], 'ro')
        return [contours, goal]

    def get_param_values(self):
        return None

    def set_param_values(self, params):
        pass

    def horizon(self):
        return None


class PointDynamics(object):
    """
    State: position.
    Action: velocity.
    """

    def __init__(self, dim, sigma):
        self.dim = dim
        self.sigma = sigma
        self.s_dim = dim
        self.a_dim = dim

    def forward(self, state, action):
        mu_next = state + action
        state_next = mu_next + self.sigma * \
                     np.random.normal(size=self.s_dim)
        return state_next
