import mock from './mock'
// import './api/v1/p2p/crypto'
// import './api/v1/p2p/fiat'
// import './api/v1/p2p/rates'
// import './api/v1/rates'
// forwards the matched request over network
mock.onAny().passThrough ()
