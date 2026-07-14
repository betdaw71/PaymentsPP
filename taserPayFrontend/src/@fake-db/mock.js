import MockAdapter from 'axios-mock-adapter'
import instance from '@/services/api'

// This sets the mock adapter on the axios instance
const mock = new MockAdapter(instance)
export default mock
